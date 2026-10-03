# Personal cloud agent environment — living spec

**Date.** 2026-10-02. **Status.** Spec written from the approved design; under independent review;
executing. **Research.** `docs/doperpowers/2026-09-30-personal-cloud-env-research.md` and the four
reports under `docs/doperpowers/research/2026-09-30-personal-cloud-env/`. **Design history.** The
brainstorm closed on 2026-10-02 after one `doperpowers:critique` round; the human then decided
GCP Secret Manager over sops+age and relay-only inference over a fallback (§Decision Log).

## Purpose

One person runs many long Claude Code sessions. Today they run on a MacBook that sleeps and a Mac
mini with 16 GB that is already swapping at nine sessions. After this work the person has an
**agent home in the cloud** — a Linux server that is *their* computer: same `~/.claude`, same
model routing, same plugins and MCP servers, same session history, and the Macs one `ssh` away —
where forty sessions keep running while the laptop is closed. Concretely: from any terminal,
`mosh devbox`, then `tmux`, then `claude`, and the session that started on the Mac yesterday is
there to resume; a seat spawned on the devbox shows up in the laptop's `/resume` list minutes
later; a tool call that needs the mini's screen reaches it through the same MCP server name.

What someone can do after, that they could not before: close the laptop with thirty seats
working; resume any session from any of the three machines; run GUI automation on the mini from a
Linux session; find a transcript from eight months ago under a dated snapshot; lose a relay for
ten minutes without losing a session.

Terms of art used in this document:
- **devbox** — the cloud Linux server (Hetzner) that is the agent's home; "body" is the server
  (disposable), "soul" is its persistent volume mounted as `/Users/new`.
- **mini** — the Mac mini at home, always on; the **hub**: it holds the inference relay, the union
  of session history, the Mac-only hands, and every controller timer.
- **laptop** — the MacBook ("SK"), a **peer**: runs sessions of its own, synced through the mini.
- **relay** — the ClaudeUsage gateway (`/Users/new/Developer/GitHub/claude-usage-menubar`, a Swift
  macOS app) that listens on `127.0.0.1:8641` on each Mac, holds the claude.ai credentials, routes
  between accounts and to GPT models; on the mini it is published to the tailnet with
  `tailscale serve` as TLS on port 8641.
- **tailnet** — the Tailscale network every machine here is on; names like `mac-mini.<tailnet>.ts.net`.
- **seat** — a background Claude Code session managed by sminos (`skills/sminos/`), spawned with
  `claude --bg`; its registry lives under `~/.claude/sminos/`.
- **session store** — `~/.claude/projects/<key>/<session-id>.jsonl` and the per-session
  directories beside it; `<key>` is the working directory's absolute path with every character
  outside `[A-Za-z0-9]` replaced by `-` (`-Users-new-Developer-GitHub-doperpowers`).
- **union** — the set of every host's session files, held on the mini and propagated by sync.
- **managed settings** — Claude Code's policy-tier settings file, root-owned, read after user
  settings and winning every collision: `/etc/claude-code/managed-settings.json` on Linux,
  `/Library/Application Support/ClaudeCode/managed-settings.json` on macOS.
- **secret handler** — `~/.claude/tools/secret-env`, defined in Interfaces.
- **hands** — tools that only work on the mini (GUI automation `cua_repl`, Chrome-extension
  Playwright, codex computer use), reached from other hosts over ssh through `~/.claude/tools/mcp-hand`.

## Progress

- [ ] M0 — Access and accounts (tailnet ACL, Hetzner token, GCP secrets and service account)
- [ ] M1 — Hub preparation on the mini (Mutagen, restic → GCS, 60-day window, watchers, jobs/ pruned)
- [ ] M2 — Laptop ⇄ mini session sync and cross-host resume
- [ ] M3 — The devbox: provisioning, identity seeding, relay-only inference, secret handler, hands wrapper
- [ ] M4 — Mini ⇄ devbox sync; seats on the devbox
- [ ] M5 — Observability timers and the outage drills
- [ ] M6 — Elasticity (server change-type), cost review, acceptance run

## Acceptance

Each item is behavior a human can verify; M6 runs them all as written (Concrete Steps carry the
exact commands).

1. **Same computer.** On the devbox, `claude --version` matches the laptop's `minimumVersion` floor
   or newer; inside a session, `/status` lists the same plugins as the laptop
   (designer, doperpowers, eli5, ptc, pyright-lsp, typescript-lsp; swift-lsp may show as failed),
   and `/mcp` lists `cua_repl` and `openaiDeveloperDocs` as connected.
2. **Relay-only inference.** A one-line prompt on the devbox (`claude -p 'reply with the word pong'`)
   returns `pong`, and the mini's ClaudeUsage panel shows the request against the routed account.
   With the relay stopped on the mini, the same command fails with a connection error and no other
   provider is contacted (no `api.anthropic.com` connection from the devbox in `ss -tnp`).
3. **One session history.** A session started on the devbox exists on the laptop within 2 minutes
   as `~/.claude/projects/<key>/<id>.jsonl`, and `claude --resume <id> --fork-session` on the laptop
   continues it with the conversation intact. The reverse (laptop → devbox) holds too.
4. **Hands.** In a devbox session, the `cua_repl` MCP server connects and
   `await cua.getState()` returns the mini's current screen state.
5. **Secrets.** On the devbox, `secret-env export devbox-github-pat` prints an `export GH_TOKEN=…`
   line and `gh auth status` succeeds; `grep -rl "$(secret-env get devbox-github-pat | cut -c1-12)" /Users/new /etc 2>/dev/null`
   finds nothing.
6. **Headroom.** With 30 seats live on the devbox (`ls ~/.claude/sessions/*.json | wc -l` ≥ 30),
   `free -g` shows at least 8 GB available and `swapon --show` is empty.
7. **Relay outage.** Restart the relay on the mini while a devbox session is mid-conversation; the
   next prompt in that session completes without any manual action once the relay is back.
8. **Long window.** Delete a transcript from the live tree on the devbox; it is still present under
   `/Users/.snapshots/<yesterday>/new/.claude/projects/<key>/`, and after copying it back
   `claude --resume <id> --fork-session` works.
9. **Disaster copy.** `restic -r gs:<bucket>:/ snapshots` lists snapshots tagged `mini` and `devbox`
   from the last 24 h; `restic restore latest --include '*/<id>.jsonl' --target /tmp/r` yields a
   byte-identical file.
10. **Conflict resolution.** Append a different line to the same
    `~/.claude/projects/<key>/memory/MEMORY.md` on the laptop and on the devbox within the same
    minute; within 5 minutes both hosts hold one winner and one
    `MEMORY.md.conflict-<host>-<timestamp>` sibling, and `mutagen sync list` on the mini reports no
    conflicts.
11. **Elasticity.** With no busy seat for 30 minutes the server type is `cax11`
    (`hcloud server describe devbox-1`); a `sminos spawn` request brings it back to `cax41` and the
    seat starts within 4 minutes; the ssh host key and the tailnet name are unchanged.
12. **Access.** From the devbox, `curl -s https://mac-mini.<tailnet>.ts.net:8641/claudeusage/state`
    answers (any HTTP status); from a test node joined with the `tag:worker` key, the same `curl`
    times out.

## 1. Architecture

```
  laptop (peer: own sessions, mosh client)                 tailnet, ACL: only tag:devbox and the laptop reach the mini
        ▲ mutagen session, initiated by the mini
        │
  mini (hub)  ◄── mutagen session, initiated by the mini ──►  devbox (agent home)
   • relay, tailscale-served :8641                             • Hetzner fsn1/nbg1 cax41 (ARM, 32 GB), Ubuntu 24.04
   • union of ~/.claude/projects, 60-day live window           • volume = /Users (btrfs zstd); /Users/new = home; /Users/.snapshots daily, 365 d
   • hands: cua, Chrome, Keychain                              • managed settings: ANTHROPIC_BASE_URL → the mini's relay
   • controller timers: sync health, conflict resolver,        • seats under tmux + sminos; worktrees per session
     relay probe, restic, disk, reaper                          • restic of the volume → GCS
   • runs few or zero seats after M4
```

The devbox holds a key to the mini only. Nothing holds a key to the laptop. All cloud and GCP
control (Hetzner API, server change-type) runs from the mini or the laptop, never from the devbox.

## 2. State classes and their mechanisms

| Class | Mechanism | Source of truth | History |
|---|---|---|---|
| Authored config (`~/.claude` whitelist: `settings.json`, `CLAUDE.md`, skills, agents, hooks, commands, keybindings, `sync/`, `tools/`) | the existing `claude-config` git repo (`~/.claude` is the clone; `sync/sync.sh` commits, rebases with a structural JSON merge, pushes); on the devbox a systemd timer runs it | git remote | git |
| Session state (`~/.claude/projects` incl. `memory/`; `~/.claude/plans`; `~/.claude/tasks`) | Mutagen `two-way-safe`, star topology, both sessions created on the mini; one writer per file; `--fork-session` on cross-host resume | the writing host per file; the mini holds the union | live window 60 days everywhere (`cleanupPeriodDays: 60` in the synced settings); devbox btrfs daily read-only snapshots kept 365 days; restic → GCS nightly from the mini and the devbox |
| Shared logs and runtime (`history.jsonl`, `sessions/`, `~/.claude.json`, `debug/`, `shell-snapshots/`, `session-env/`, `paste-cache/`, `file-history/`, `jobs/`, `.credentials.json`, tailscaled state) | host-local, excluded from every sync | each host | none (the devbox's snapshots catch them incidentally) |
| Caches (`plugins/`, package caches) | rebuilt per host by `~/.claude/sync/apply.py` from `sync/plugins.manifest.json` and `sync/mcp.json` | the manifest in git | git |
| Secrets | the secret handler against GCP Secret Manager (§5) | GCP Secret Manager, project `ytdownload-505811` | secret versions |
| Repositories | git; canonical clones under `/Users/new/Developer/GitHub/<repo>`, worktrees per session; work in progress pushed to `wip/<host>` branches | git remotes | git |
| Device-bound capabilities | hands over ssh to the mini (§7) | the mini | — |

Why by class and not by machine: each row has a different writer pattern; one mechanism for all
of them is how mirrors corrupt (`~/.claude.json` rewritten whole by two hosts, pid registries that
clear each other, a refresh token that logs the other machine out). Path identity makes the second
row portable: user `new`, uid 501, home `/Users/new`, repositories under
`/Users/new/Developer/GitHub/<repo>` on every host, because the session store's key, transcript
`cwd` fields, file-history paths, plugin registries and trust records all carry absolute paths.

## 3. The devbox

**Server.** Hetzner Cloud, project `devbox`, location `fsn1` (fallback `nbg1`), server `devbox-1`,
type `cax41` (16 vCPU ARM, 32 GB, 320 GB local NVMe; €41.49/month at 2026-10 prices), image
`ubuntu-24.04`, volume `devbox-home` 100 GB with delete protection. Why cloud at all and why this
one: the mini's 16 GB caps sessions at about nine (measured: 9 sessions = 4.6 GB RSS plus swap in
use), a 32 GB Linux box holds ~40 at the measured ≈0.5 GB per session; CAX is the cheapest 32 GB
on offer (US and Singapore x86 equivalents are 3–6× the price); the named alternatives — a 64 GB
Mac mini (no sync, no standby, ≈₩3M) and a home Linux box (no rent, LAN latency, same home
dependence) — lost on elasticity and on wanting to learn the cloud shape, and stay named. Stated
trade-off: 250–300 ms round trip from Korea on every keystroke and every hand call; Hetzner
repriced 30–175% in 2026 without grandfathering.

**Body and soul.** The server is disposable; everything that must survive lives on the volume
(the shape `infra/worker-host/` already uses, "body / soul / seeding"). The volume is btrfs with
`compress=zstd:3,noatime`, mounted at `/Users`, with subvolumes `home` (mounted at `/Users/new`)
and `snapshots` (at `/Users/.snapshots`). btrfs over ZFS because it is in-kernel: ZFS is a DKMS
module on a body that takes unattended kernel updates, and a failed module build leaves the volume
unmounted. Daily read-only snapshots of `home` kept 365 days are the long online window for
transcripts (append-only files at 4.2× zstd pin almost nothing per snapshot). Hetzner's own
volume snapshots do not exist, which is why btrfs carries this. The volume is Ceph-backed
(5,000 IOPS / 200 MB/s); whether worktrees, `jobs/` and the plugin cache move to the local NVMe
(bind-mounted under the home) is decided by an fio measurement in M3.

**Provisioning** is `infra/devbox/cloud-init.yaml` plus `infra/devbox/provision.sh` (run on the
laptop with the hcloud context) and `infra/devbox/seed.sh` (run once per volume, on the devbox).
cloud-init: hard gate that `/Users` is a mountpoint; btrfs format only when the volume is blank;
user `new` uid 501 home `/Users/new` (`snap set system homedirs=/Users`; no snaps used); packages
git, build-essential, python3, python3-venv, jq, unzip, ca-certificates, tmux, mosh, restic, rclone,
btrfs-progs, fio; Node 22 via nvm as `new` (same as the Macs); `gh` from its apt repo; `claude` by
the native installer as `new`; Tailscale; hostname `devbox-<machine-id[:6]>` (unique per body so
sminos' host-aware liveness treats a rebuilt body's old pids as dead; `/etc/machine-id` is never
persisted); the ssh host key restored from `/Users/.ssh-host/` so peers see one host across
bodies; `ufw` allowing inbound only on `tailscale0` after the node has joined. The join is not in
cloud-init: user-data is stored in plaintext by the provider, so `provision.sh` joins the node
after first boot over ssh as root, reading the auth key on the laptop through the secret handler
and streaming it to a tmpfs file on the server (`tailscale up --auth-key file:/run/ts.key`,
then `shred`). The managed-settings file (§4) is written by cloud-init. `seed.sh` does the once-per-volume work: clone
`claude-config` into `/Users/new/.claude`, run `sync/apply.py`, install the systemd timer for
`sync/sync.sh`, seed `~/.claude.json` from `sync/claude-json.template.json` (trust for the canonical
clones, user-scope MCP servers), clone the canonical repositories, `gh auth` through the handler,
git identity, write the devbox's ssh key (`/Users/new/.ssh/id_ed25519`, created here, public half
to be authorized on the mini by M3's human step), create `/Users/.snapshots` and install the
snapshot timer.

**Inference.** Relay only — the human's decision; no second provider. The synced
`settings.json` keeps `ANTHROPIC_BASE_URL=http://127.0.0.1:8641` and the non-secret relay marker
`claudeusage-local-gateway` as `ANTHROPIC_AUTH_TOKEN` (the relay README says the marker is not an
access-control secret; the relay replaces it with the routed account's credential). On the devbox,
managed settings override `env.ANTHROPIC_BASE_URL` to `https://mac-mini.<tailnet>.ts.net:8641`.
This works because Claude Code applies settings `env` onto the process environment in precedence
order with policy last (read in the 2.1.283 source; M3 confirms it on Linux), so the synced file
is untouched and every seat inherits the override. No proxy process. Consequence: when the relay
is unreachable the devbox has no inference — sessions retry connection errors and continue when
it returns; a turn in flight during an outage is lost like any process kill. The standby property
("home dark, devbox keeps working") is not provided and is not claimed. The alternatives that
lost: a socat forward (adds a process for nothing once there is one backend) and HAProxy with a
`api.anthropic.com` + setup-token fallback (the critique's shape; rejected by the human, recorded
in the Decision Log for the day a fallback is wanted). A Linux build of the relay's gateway target
(`Sources/ClaudeUsageGateway/`, a separate Swift target with a `CredentialSource` protocol) is the
mature route to a devbox-local relay and a separate goal.

**Sessions.** Interactive: `mosh devbox` → `tmux` → `claude`. Detached: sminos seats spawned on
the devbox (`sminos spawn …` run there), registry on the volume, host-stamped. Cross-session
messaging (`ListAgents`/`SendMessage`) works among seats on the devbox as on one computer.
Spawning a seat on the devbox *from* the laptop (`sminos spawn --host`) is residue for a ticket,
not this spec. Remote Control is not used: it refuses to run when `ANTHROPIC_BASE_URL` is not
`api.anthropic.com` (confirmed: every recent session's debug log shows `bridge not enabled`).

## 4. Per-host divergence

Exactly one mechanism: managed settings. On the devbox,
`/etc/claude-code/managed-settings.json` (root, 0644) is:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://mac-mini.<tailnet>.ts.net:8641"
  }
}
```

Nothing else differs per host. `cleanupPeriodDays` is deliberately *not* overridden anywhere: the
sweep deletes files and Mutagen propagates deletions, so the smallest value on any host is the
window everywhere; the synced value is the only value.

## 5. Secrets

Backend: GCP Secret Manager in project `ytdownload-505811` (the human's choice over sops+age; the
trade is a service-account key on the devbox and a network dependency at session start, for a
console with audit, versions and rotation). The handler is `~/.claude/tools/secret-env` (Interfaces
§I1): python, `google-auth` in a venv it bootstraps under `~/.claude/tools/.venv-secret-env`,
REST call `GET https://secretmanager.googleapis.com/v1/projects/<p>/secrets/<name>/versions/latest:access`,
values held in memory and, optionally, in a tmpfs cache (`/dev/shm/secret-env-<uid>/`, mode 0700,
TTL 10 minutes) so forty seats starting at once do not make forty calls. Authentication: the
laptop and the mini use Application Default Credentials (the laptop already has them; the mini
gets them once with `gcloud auth application-default login`, a human step because it opens a
browser); the devbox has no GCP identity and Hetzner has no OIDC issuer, so it uses one
service-account key file `/Users/new/.config/gcloud/devbox-secrets.json` (0600) for the service
account `devbox-secrets@ytdownload-505811.iam.gserviceaccount.com` with role
`roles/secretmanager.secretAccessor` on that project only. That file is the devbox's one root
secret, seeded by hand once per volume (M3).

Secrets and names: `devbox-github-pat` (one GitHub account credential for every repository —
the human's decision over per-repo tokens; exposed as `GH_TOKEN`; git authenticates through
`gh auth setup-git`), `devbox-tailscale-authkey` (ephemeral, reusable, pre-authorized, tagged
`tag:devbox`; consumed at join), `restic-password` (one restic repository for both hosts). The
Hetzner token is not in the vault: it stays in the hcloud CLI context on the laptop and the mini
(`~/.config/hcloud/cli.toml`, 0600) and never reaches the devbox. The relay marker is not a secret.
No plaintext secret in any repository or on the devbox disk; commands that load secrets read from
files or the handler, never from arguments that land in a transcript.

## 6. Sync, windows, archives

**Mutagen** (0.18.x, the last release; unmaintained since 2025-02, so the ignore set and conflict
policy below are kept tool-agnostic and Syncthing is the named replacement) is installed on the
mini only (`brew install mutagen`). The mini creates two sessions, `claude-sk` and `claude-devbox`
(Interfaces §I3): mode `two-way-safe` (a conflict is recorded and the file stops syncing; never
`two-way-resolved`, which lets the alpha side overwrite the other side's appended lines); roots
`~/.claude/projects`, `~/.claude/plans`, `~/.claude/tasks` as three roots per peer; ignore
`**/.DS_Store`, `**/*.tmp`, `**/*.lock`. The excluded classes of §2 are outside these roots by
construction. Peers need only sshd: the laptop with Remote Login on, reached as `sk` over the
tailnet; the devbox as `devbox`. Why the mini initiates: it is the one always-on machine, and a
recreated or re-typed devbox resumes the same session because its host key and tailnet name
persist.

**Conflicts.** `memory/*.md` and `plans/*.md` are written by sessions on every host, so conflicts
happen. A launchd timer on the mini (`com.user.hub-mutagen-conflicts`, every 2 minutes) runs
`infra/hub/mutagen-resolve-conflicts.sh` (Interfaces §I4): for each conflict Mutagen reports, keep
the side with the newer mtime, move the loser on its own host to `<name>.conflict-<host>-<UTC ts>`
beside it (the move clears the conflict and the renamed copy syncs as a new file), and notify
only when the same path conflicts three times in a day. Why not relocate memory into
`claude-config`: `sync/sync.sh` aborts the whole pull on any non-JSON conflict, so one markdown
conflict would stall all config sync.

**Windows.** `cleanupPeriodDays: 60` in the synced `settings.json` (today 36500). The sweep is
mtime-based and runs at session launch; deletions propagate, so the smallest disk bounds the
window: the mini has 113 GB free against 1–1.5 GB/day from three hosts. If the window must grow,
`projects/` moves to an external NVMe on the mini (named alternative, not done here). The devbox's
daily read-only btrfs snapshot of `home` (`infra/devbox/snapshot.sh`, systemd timer at 03:00 UTC,
prune older than 365 days) is the long online window: a swept transcript is still at
`/Users/.snapshots/<YYYY-MM-DD>/new/.claude/projects/<key>/<id>.jsonl`, greppable, and resumable
after `cp` back under `projects/<key>/` with `--fork-session` (resume by id scans `projects/*`).

**Disaster copy.** restic to one Google Cloud Storage bucket in the same GCP project
(`gs:<bucket>:/`, bucket class Nearline, name chosen at M1 and recorded in Interfaces §I5),
authenticated with the same service-account key on the devbox and ADC on the mini, password from
the handler. Nightly: the mini backs up `~/.claude/projects`, `plans`, `tasks` (the union) tagged
`mini`; the devbox backs up `/Users/new` minus `.claude/plugins`, `.cache`, `node_modules`, `jobs`
tagged `devbox`. Why GCS and not B2: no new vendor, the service account already exists. Time
Machine is not used for `projects/` (`tmutil addexclusion`): whole-file hourly copies of 80 MB
transcripts would churn tens of GB a day, and the mini has no Time Machine destination today.

**To verify in M2:** Mutagen preserves mtime on the receiving side. If it stamps arrival time, a
re-seeded peer restarts the window for everything it receives (harmless for live transcripts,
which arrive seconds after their last append).

## 7. Hands and security

- The devbox's ssh key (`/Users/new/.ssh/id_ed25519`, created in `seed.sh`) is authorized on the
  mini only, as `from="100.64.0.0/10" ssh-ed25519 …` in `/Users/new/.ssh/authorized_keys`, so an
  exfiltrated key works only from a tailnet address. It is a full-shell key: GUI automation of the
  mini is full control of the mini anyway, and general `ssh mini bash`/python-heredoc hands are
  the point. The laptop is the hard boundary: nothing reaches it.
- Mac-bound stdio MCP servers run through `~/.claude/tools/mcp-hand <server>` (Interfaces §I2),
  which execs the server locally on Darwin and `ssh -o BatchMode=yes mini …` elsewhere. The
  manifest `~/.claude/sync/mcp.json` names the wrapper for `cua_repl` so every host carries the
  same entry (the Macs' existing direct entries are replaced once with `claude mcp remove` +
  `apply.py`). Preconditions on the mini: auto-login GUI session (already so), ChatGPT.app resident
  for cua, per-app approvals pre-granted (`CUA_SHIM_PERSIST=always` in the wrapper's env for the
  server). The Chrome profile the Playwright extension uses lives on the mini (not done here;
  `cua_repl` is the hand this spec proves).
- **Tailnet ACL (M0, before anything else).** The tailnet carries ~890 ephemeral `writer-`/
  `chapter-` nodes from other projects; the relay is published tailnet-wide with no client
  authentication, so any of them can draw on every claude.ai account while online. Policy
  (Interfaces §I6): tags `tag:devbox`, `tag:worker`; the laptop and `tag:devbox` may reach
  `mac-mini:8641` and `mac-mini:22`; `tag:worker` reaches nothing on the Macs; the laptop and the
  mini may reach `tag:devbox:22,60001-60010` (ssh, mosh). The human applies the policy in the
  admin console (no API key is created for this).
- No Hetzner write-capable token on the devbox. Server change-type, the reaper, and every
  `hcloud` call run on the mini (controller) or the laptop (operator). The volume has delete
  protection on.
- A richer remote-file MCP (read with image/PDF content blocks, edit with read-before-write
  tracking) is a separate later goal.

## 8. Observability and elasticity

- Timers on the mini (launchd, labels in Interfaces §I4): Mutagen health and conflicts (2 min),
  relay reachability as the devbox sees it (`ssh devbox curl …/claudeusage/state`, 5 min),
  restic (nightly 04:00 KST), disk headroom on the mini and the volume (hourly; warn under 20 GB),
  reaper (5 min, M6). Notification through the existing `~/.claude/hooks/notify.sh`
  (terminal-notifier + osascript); a push channel is optional and not done here.
- Elasticity (M6): `hcloud server change-type devbox-1 cax11 --keep-disk` when no seat has been
  busy for 30 minutes and `… cax41` on the next spawn request, both from the mini
  (`infra/hub/devbox-scale.sh`). Same host identity, host key, tailnet node, Mutagen session; the
  idle cost is ≈€4/month instead of €41. Both directions need a power-off, so tmux sessions end:
  the reaper first retires idle seats to their transcripts (`sminos retire`), and running
  interactive sessions block the downscale (a tmux client attached counts as busy). Delete-and-
  recreate from a snapshot image is the alternative that lost (an image to keep fresh, a new host
  identity each time).
- `claude` auto-updates on every host; `minimumVersion` in the synced settings bounds skew.

## 9. Execution

### Constraints that bind every milestone

- **Two repositories.** Infra and scripts for the hub and the devbox live in this repository
  under `infra/hub/` and `infra/devbox/`, on branch `personal-cloud-env` in the isolated worktree
  `.claude/worktrees/personal-cloud-env/` (created from `origin/main` after this spec was pushed).
  Tools that must exist on every host at the same path (`secret-env`, `mcp-hand`, the
  `~/.claude.json` template, the systemd units for config sync, the manifest change) live in the
  `claude-config` repository, i.e. in `~/.claude` on the laptop, committed directly on its `main`
  (its `sync/sync.sh` rebases `main` every 30 minutes; a feature branch there would fight the
  sync). Each such commit is named in Progress with its short SHA.
- **Path identity** on every host: user `new`, uid 501, home `/Users/new`, repositories under
  `/Users/new/Developer/GitHub/<repo>`.
- **The synced `settings.json` is never edited per host.** Per-host divergence only through
  managed settings (§4).
- **Secrets** are never written in plaintext to any repository or to the devbox disk (the one
  service-account key excepted), never passed as command-line arguments, never echoed; commands
  read them from files the human places or from the handler.
- **No Hetzner write-capable token on the devbox.** Every `hcloud` call runs on the laptop or the mini.
- **One writer per transcript file.** Cross-host resume is always `--fork-session`.
- **Human-only steps** (the tailnet ACL in the admin console, the Hetzner token, the GitHub PAT,
  `gcloud auth application-default login` on the mini, Remote Login on the laptop, authorizing the
  devbox key on the mini) are escalated with the exact instruction text; the executor waits, then
  verifies.
- **Platform floors:** Claude Code ≥ 2.1.283 everywhere (managed-settings `env` precedence was read
  there); Ubuntu 24.04 arm64; macOS 27; Mutagen 0.18.x; Node 22; hcloud CLI ≥ 1.69.
- **Nothing in this spec runs on the laptop's `main` of this repository without the branch
  review** (`doperpowers:review-code` at the medium rung, Decision Log).

### Plan of Work

#### M0 — Access and accounts

What exists at the end: the tailnet denies the worker tags any path to the Macs and admits the
devbox tag; the laptop holds an hcloud context for the `devbox` project; GCP holds the three
secrets and the `devbox-secrets` service account with a downloaded key on the laptop (not yet on
any devbox); the price and availability of `cax41` in `fsn1`/`nbg1` are confirmed from the API.
Touches: `infra/hub/tailnet-policy.hujson` (the policy text the human pastes), `infra/devbox/README.md`
(the operator runbook, started here). Decisions: GitHub PAT is a fine-grained token on the one
account with contents read/write, pull requests, issues, workflows on all repositories, 1-year
expiry (the human creates it and places it at `~/.config/devbox/github-pat` 0600; the executor
uploads with `--data-file` and shreds the file); the Tailscale auth key is reusable, ephemeral,
pre-authorized, `tag:devbox` (human creates it in the admin console, places it at
`~/.config/devbox/tailscale-authkey`); `restic-password` is generated (`openssl rand -base64 32`)
straight into the secret, never shown. Does not touch: the mini, the devbox, any sync.
Proves: acceptance 12 (policy half; the negative test runs in M6 with a throwaway node).

#### M1 — Hub preparation on the mini

What exists at the end: the mini runs Mutagen and restic, has ADC for GCP, backs up the union
nightly to the GCS bucket, has `cleanupPeriodDays: 60` through the synced settings, `projects/`
excluded from Time Machine, the conflict resolver and disk-headroom timers loaded, and `jobs/`
pruned on both Macs (the 20 GB `jobs/bb761c28/tmp` on the laptop and whatever the mini holds).
Touches: `infra/hub/` (`install.sh`, `mutagen-resolve-conflicts.sh`, `restic-backup.sh`,
`disk-headroom.sh`, `relay-probe.sh`, launchd plists under `infra/hub/launchd/`), the synced
`~/.claude/settings.json` (`cleanupPeriodDays`, one commit in `claude-config`), the mini's
`~/.config/hcloud` (context copied from the laptop by the human or created with the token).
Decisions: the GCS bucket is created here (`gsutil mb -c nearline -l asia-northeast3`), named
`devbox-restic-<6 random hex>` and recorded in Interfaces §I5; restic repository initialized from
the mini with the password read through the handler; launchd plists are installed by `install.sh`
into `~/Library/LaunchAgents/` and loaded with `launchctl bootstrap gui/501`; the pruning of
`jobs/` deletes only `jobs/*/tmp` directories older than 7 days plus the known 20 GB one; the
`cleanupPeriodDays` change lands first on the laptop (synced repo) and the executor confirms the
mini received it before any sync session exists. Does not touch: the laptop's sshd, any Mutagen
session (M2), the devbox. Proves: acceptance 9 (mini half), the timers of acceptance 10 exist.

#### M2 — Laptop ⇄ mini session sync and cross-host resume

What exists at the end: Mutagen session `claude-sk` runs on the mini with the three roots; a
session created on either Mac appears on the other within 2 minutes; `--fork-session` resume
works both ways; the mtime question is answered in Surprises & Discoveries; the conflict resolver
has resolved one induced conflict. Touches: `infra/hub/mutagen-sessions.sh` (creates/updates the
named sessions idempotently), the laptop's Remote Login (human: System Settings → General →
Sharing → Remote Login, or `sudo systemsetup -setremotelogin on`), `~/.ssh/config` on the mini
(`Host sk` → the laptop's tailnet name, user `new`). Decisions: the laptop is `beta` and the mini
`alpha` in every session (the mini is the union; naming only, no precedence under `two-way-safe`);
the initial scan of ~55k files is allowed to take minutes; sessions are created with
`--ignore-vcs` off (no `.git` under these roots) and `--symlink-mode ignore`. Does not touch: the
devbox; `cleanupPeriodDays`. Proves: acceptance 3 (Mac half), 10.

#### M3 — The devbox

What exists at the end: `devbox-1` runs in `fsn1` with the `devbox-home` volume mounted at
`/Users`, user `new` with the synced `~/.claude`, plugins and MCP servers installed, managed
settings pointing inference at the mini's relay, the secret handler returning `GH_TOKEN`, `gh`
authenticated, canonical clones present and trusted, the daily btrfs snapshot timer and the
restic timer installed, the devbox's key authorized on the mini, `cua_repl` reachable from a
devbox session, and an fio verdict for the volume versus the local NVMe. Touches:
`infra/devbox/cloud-init.yaml`, `infra/devbox/provision.sh`, `infra/devbox/seed.sh`,
`infra/devbox/snapshot.sh`, `infra/devbox/README.md`; in `claude-config`: `tools/secret-env`,
`tools/mcp-hand`, `tools/hands.json`, `sync/claude-json.template.json`, `sync/apply.py` (seed trust
from the template when `~/.claude.json` is absent), `sync/mcp.json` (`cua_repl` → `mcp-hand`),
`sync/claude-config-sync.{service,timer}`, `sync/install-systemd.sh`. Decisions: the managed
settings file is written by cloud-init from `provision.sh`'s `--relay-url` argument; `seed.sh`
reads the service-account key from `/Users/new/.config/gcloud/devbox-secrets.json`, which the
human copies in with `scp` before `seed.sh` runs (the one hand-seeded secret); the Tailscale join
is `provision.sh`'s last step over ssh (`tailscale up --auth-key file:/run/ts.key --ssh=false
--hostname=devbox`, the key streamed from the laptop's `secret-env get devbox-tailscale-authkey`
into `/run/ts.key` and shredded after), followed by enabling ufw; the devbox's
public key is printed at the end of `seed.sh` for the human to authorize on the mini with the
`from=` prefix (exact line given); fio runs `--rw=randrw --bs=4k --iodepth=32 --size=2G` on both
disks and the verdict decides whether `provision.sh` gains the NVMe bind-mounts (recorded, not
implemented here unless the volume fails the `npm ci` test of the doperpowers clone under 90 s).
`swift-lsp` is allowed to fail on Linux. Does not touch: Mutagen sessions to the devbox (M4), the
reaper. Proves: acceptance 1, 2, 4, 5, 8 (snapshot half), 12 (devbox half).

#### M4 — Mini ⇄ devbox sync; seats on the devbox

What exists at the end: Mutagen session `claude-devbox` runs; sessions started on the devbox
appear on both Macs and vice versa; 30 seats run on the devbox (`sminos spawn` executed on the
devbox over `mosh`/`ssh`, a trivial task each) with the headroom of acceptance 6; the mini's own
seats are retired to the devbox (the human decides which; the executor retires none without
instruction); cross-session messaging between two devbox seats works. Touches:
`infra/hub/mutagen-sessions.sh` (second session), `infra/devbox/README.md` (how to spawn and
attach). Decisions: seats are spawned with the doperpowers worktree skill's layout under the
canonical clones; the 30-seat load test uses `sminos spawn load-<n> "reply done and stop"` and is
retired afterwards. Does not touch: sminos' code (no `--host`). Proves: acceptance 3 (devbox half),
6, 9 (devbox half).

#### M5 — Observability and the outage drills

What exists at the end: the relay-probe timer notifies within 10 minutes of the relay becoming
unreachable from the devbox; the restic restore of one transcript from GCS is demonstrated; the
relay-restart drill and the mini-off drill are run and recorded (what a devbox session does
during each, how long until recovery); the btrfs snapshot restore is demonstrated. Touches:
`infra/hub/relay-probe.sh`, `infra/devbox/README.md` (drill transcripts). Decisions: the
mini-off drill is 10 minutes of the relay app quit (not the mini powered off); recovery is
measured from relay start to the devbox session's next completed turn. Does not touch: anything
structural. Proves: acceptance 7, 8, 9.

#### M6 — Elasticity, cost review, acceptance

What exists at the end: `infra/hub/devbox-scale.sh` and the reaper timer; the devbox has been
scaled down to `cax11` and back to `cax41` with its identity intact; a throwaway `tag:worker` node
has shown the ACL denying the relay; the cost of the first weeks is written into the
retrospective; and every acceptance item has been run as written with its output recorded in
Concrete Steps. Touches: `infra/hub/devbox-scale.sh`, `infra/hub/launchd/com.user.hub-reaper.plist`,
`infra/devbox/README.md`. Decisions: "busy" is any seat whose sminos live state is `busy` or any
tmux session with an attached client, read over ssh; the reaper downscales after 30 minutes of
not-busy and never while `mutagen sync list` shows a session mid-flush; the upscale trigger is a
`sminos spawn` wrapper on the mini (`infra/hub/devbox-spawn.sh`) that scales up, waits for ssh,
then runs the spawn over ssh. Does not touch: sminos' code. Proves: acceptance 11, 12 (negative
half), and runs 1–12.

### Concrete Steps

Working directory for every laptop command: `/Users/new/Developer/GitHub/doperpowers` on the
spec's branch worktree unless stated. Expected transcripts are abbreviated; the executor records
the real ones here as milestones complete.

M0
```
# human: Hetzner console → project "devbox" → API token (Read & Write) → then in this session:
! hcloud context create devbox
hcloud server-type list -o columns=name,cores,memory,disk,architecture | grep -i cax     # cax41 16 32 320 arm
hcloud server-type describe cax41 | grep -A3 fsn1                                        # hourly/monthly price shown
# GCP (laptop ADC):
gcloud --project ytdownload-505811 services enable secretmanager.googleapis.com
gcloud --project ytdownload-505811 iam service-accounts create devbox-secrets --display-name "devbox secret accessor"
gcloud projects add-iam-policy-binding ytdownload-505811 --member serviceAccount:devbox-secrets@ytdownload-505811.iam.gserviceaccount.com --role roles/secretmanager.secretAccessor
gcloud --project ytdownload-505811 iam service-accounts keys create ~/.config/devbox/devbox-secrets.json --iam-account devbox-secrets@ytdownload-505811.iam.gserviceaccount.com
gcloud --project ytdownload-505811 secrets create devbox-github-pat --data-file ~/.config/devbox/github-pat && shred -u ~/.config/devbox/github-pat
gcloud --project ytdownload-505811 secrets create devbox-tailscale-authkey --data-file ~/.config/devbox/tailscale-authkey && shred -u ~/.config/devbox/tailscale-authkey
openssl rand -base64 32 | gcloud --project ytdownload-505811 secrets create restic-password --data-file -
gcloud --project ytdownload-505811 secrets list                                           # three names
# human: Tailscale admin console → Access controls → paste infra/hub/tailnet-policy.hujson → Save
```

M1 (on the mini, via `ssh mini`)
```
brew install mutagen restic
gcloud auth application-default login            # human: browser
bash infra/hub/install.sh                        # copies scripts to ~/.local/hub, installs launchd plists
launchctl list | grep com.user.hub               # four labels
tmutil addexclusion ~/.claude/projects
restic -r gs:<bucket>:/ init                     # password via secret-env
restic -r gs:<bucket>:/ snapshots                # empty list, no error
```

M2 (on the mini)
```
bash infra/hub/mutagen-sessions.sh sk            # creates claude-sk
mutagen sync list                                # Status: Watching for changes
# on the laptop: claude -p 'say hi' in a repo dir; within 2 min on the mini:
ls ~/.claude/projects/-Users-new-Developer-GitHub-doperpowers/ | tail -1
claude --resume <id> --fork-session -p 'what did I say?'   # answers "hi"
```

M3 (laptop, then devbox)
```
bash infra/devbox/provision.sh --location fsn1 --type cax41 --relay-url https://mac-mini.<tailnet>.ts.net:8641
# prints the server's tailnet name once cloud-init finishes; then
scp ~/.config/devbox/devbox-secrets.json devbox:/Users/new/.config/gcloud/devbox-secrets.json
ssh devbox 'bash -lc "bash ~/doperpowers/infra/devbox/seed.sh"'     # ends by printing the public key line to authorize on the mini
# human: append that line to /Users/new/.ssh/authorized_keys on the mini
mosh devbox
claude -p 'reply with the word pong'            # pong
claude mcp list                                  # cua_repl: connected
```

M4–M6: commands as the milestones state; recorded here when run.

### Interfaces and Dependencies

**I1 — `~/.claude/tools/secret-env`** (python 3.11+, `google-auth`, `requests`; venv bootstrapped
on first run). Commands:
- `secret-env get <name>` — prints the secret value, no newline, exit 1 if absent.
- `secret-env export <name>…` — prints `export <ENV>=<value>` lines where `<ENV>` is the name
  upper-cased with `-`→`_`, except `devbox-github-pat` → `GH_TOKEN` and `restic-password` →
  `RESTIC_PASSWORD` (a mapping table at the top of the script).
- `secret-env run <name>… -- <cmd>…` — execs `<cmd>` with those variables set.
Environment: `SECRET_ENV_BACKEND` (`gcpsm` default; `sops` reserved), `SECRET_ENV_GCP_PROJECT`
(default `ytdownload-505811`), `GOOGLE_APPLICATION_CREDENTIALS` (the devbox's key file), cache
dir `/dev/shm/secret-env-<uid>` on Linux and `$TMPDIR/secret-env-<uid>` on macOS, TTL 600 s,
`SECRET_ENV_NO_CACHE=1` disables it. Errors: missing credentials → exit 2 with one line on stderr;
HTTP 403/404 → exit 1 naming the secret, never the value.

**I2 — `~/.claude/tools/mcp-hand <server>`** reads `~/.claude/tools/hands.json`:
```json
{
  "cua_repl": {
    "host": "mini",
    "command": "node",
    "args": ["/Users/new/.claude/tools/cua-shim.mjs"],
    "env": {"CUA_SHIM_CODEX_HOME": "/Users/new/.maws/cua-home", "CUA_SHIM_PERSIST": "always"}
  }
}
```
On Darwin it execs `command args` with `env` directly (the Macs are the hand); elsewhere it
execs `ssh -o BatchMode=yes -o ServerAliveInterval=30 <host> env K=V… command args`, stdio passed
through. `sync/mcp.json`'s `cua_repl` entry becomes
`{"type":"stdio","command":"/Users/new/.claude/tools/mcp-hand","args":["cua_repl"]}`.

**I3 — Mutagen sessions** (created by `infra/hub/mutagen-sessions.sh <peer>`), for peer `sk`
(laptop) and `devbox`, one session per root, named `claude-<peer>-<root>`:
`mutagen sync create --name claude-<peer>-projects --sync-mode two-way-safe --symlink-mode ignore --ignore '**/.DS_Store' --ignore '**/*.tmp' --ignore '**/*.lock' ~/.claude/projects new@<peer>:/Users/new/.claude/projects`,
likewise for `plans` and `tasks`. `mutagen sync list --template '{{json .}}'` is the status source
the timers read.

**I4 — Hub timers** (launchd, `~/Library/LaunchAgents/`, installed by `infra/hub/install.sh`;
scripts copied to `~/.local/hub/`):
| Label | Interval | Script | Notifies when |
|---|---|---|---|
| `com.user.hub-mutagen-conflicts` | 120 s | `mutagen-resolve-conflicts.sh` | same path conflicts ≥3 times in 24 h; any session not `Watching for changes` for 10 min |
| `com.user.hub-relay-probe` | 300 s | `relay-probe.sh` | `ssh devbox curl -s -o /dev/null -w '%{http_code}' https://mac-mini.<tailnet>.ts.net:8641/claudeusage/state` returns `000` twice in a row |
| `com.user.hub-restic` | daily 04:00 KST | `restic-backup.sh` | non-zero exit |
| `com.user.hub-disk` | 3600 s | `disk-headroom.sh` | free < 20 GB on the mini's data volume or on `ssh devbox df /Users` |
| `com.user.hub-reaper` (M6) | 300 s | `devbox-scale.sh reap` | a change-type fails |
Notification: `~/.claude/hooks/notify.sh "<title>" "<message>"` (exists on both Macs).

**I5 — restic.** Repository `gs:<bucket>:/`; bucket name recorded here by M1:
`devbox-restic-______`. Env on both hosts: `RESTIC_REPOSITORY`, `RESTIC_PASSWORD` via
`secret-env export restic-password`, `GOOGLE_APPLICATION_CREDENTIALS` on the devbox, ADC on the
mini (`GOOGLE_PROJECT_ID=ytdownload-505811`). Retention: `restic forget --keep-daily 90 --keep-weekly 52 --prune` weekly.

**I6 — Tailnet policy** (`infra/hub/tailnet-policy.hujson`, applied by the human): tag owners
`tag:devbox`, `tag:worker` → the account; ACL rules: `autogroup:member` → `*:*` is **removed**;
`autogroup:member` → `tag:devbox:*`, `mac-mini:*`, `<laptop>:*`; `tag:devbox` → `mac-mini:22,8641`;
`tag:worker` → the workers' own services only (whatever the writer/chapter nodes need between
themselves, copied from the current policy; nothing on the Macs). The executor drafts it from the
current policy the human pastes into `infra/hub/tailnet-policy.current.hujson` (gitignored).

**I7 — Hetzner objects.** Project `devbox`; server `devbox-1`; volume `devbox-home` (100 GB,
`--protection delete`); server type `cax41` (busy) / `cax11` (idle); image `ubuntu-24.04`;
location `fsn1`; firewall none (ufw on the host). `provision.sh` arguments: `--location`, `--type`,
`--relay-url`, `--volume-size` (default 100). It is idempotent: an existing volume is reused, an
existing server is left alone.

**I8 — Devbox files.** `/etc/claude-code/managed-settings.json` (§4);
`/Users/.ssh-host/ssh_host_ed25519_key{,.pub}` (restored into `/etc/ssh/` by cloud-init when
present, generated and saved there on first boot otherwise); `/Users/.snapshots/<YYYY-MM-DD>` (btrfs
read-only snapshots of `/Users/new`'s subvolume); `/Users/new/.config/gcloud/devbox-secrets.json`;
systemd units `claude-config-sync.timer` (30 min), `devbox-snapshot.timer` (03:00 UTC),
`devbox-restic.timer` (19:00 UTC = 04:00 KST).

## Surprises & Discoveries

- Observation: `cleanupPeriodDays` was unset on both Macs until 2026-10-02 (30-day default sweep
  live; the oldest transcript was exactly 30 days old), then set to 36500 by a sync from SK.
  Evidence: `git log -S cleanupPeriodDays -- settings.json` in `~/.claude` → `63c4fd8 2026-10-02`.
- Observation: the relay marker in `settings.json` is not a secret.
  Evidence: `claude-usage-menubar/README.md:315-319`, "the marker is not an access-control secret".
- Observation: Remote Control is silently inactive on this laptop despite `remoteControlAtStartup: true`.
  Evidence: every recent `~/.claude/debug/<sid>.txt` carries `[bridge:repl] Skipping: bridge not enabled`.

## Decision Log

- Decision: Verification for this spec — one independent spec review by the
  `doperpowers:adversarial-reviewer` agent (technical-heavy spec) and, because the execution
  section has seven milestones, the same agent's buildability review of the execution section;
  the branch gets `doperpowers:review-code` at the **medium** rung at the end (infra scripts and
  configuration, a focused diff). A critique debate on the design already ran in brainstorming.
  Rationale: the stakes are a person's own machines and accounts; the code volume is small.
  Date/Author: 2026-10-02, the design session.
- Decision: GCP Secret Manager as the secrets backend, over sops+age inside `claude-config`.
  Rationale: the human's choice; the trade (a service-account key on the devbox, network at session
  start) is accepted for console, audit, versions and rotation; the handler keeps the backend
  pluggable. Date/Author: 2026-10-02, the human.
- Decision: relay-only inference on the devbox; no `api.anthropic.com` fallback.
  Rationale: the human's choice ("gateway only"); keeps one inference source per host and the
  relay's ledger authoritative. Rejected then: HAProxy on `127.0.0.1:8641` with a setup-token
  fallback backend (connection-level failover only) — recorded here as the shape to adopt if a
  standby is ever wanted. Consequence accepted: no standby when the mini is down.
  Date/Author: 2026-10-02, the human.
- Decision: one GitHub account credential for every repository, no per-repo tokens.
  Rationale: the human's choice; the earlier worker-host "two tokens, two scopes" split is dropped
  for this environment. Date/Author: 2026-10-02, the human.
- Decision: restic to a GCS bucket in the same GCP project, not Backblaze B2.
  Rationale: no new vendor; the service account and ADC already exist. Date/Author: 2026-10-02, the
  design session (silent, mechanical).

## Outcomes & Retrospective

Pending — written at finish.
