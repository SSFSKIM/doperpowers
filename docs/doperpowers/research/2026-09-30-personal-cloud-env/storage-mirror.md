# Mirroring a Mac's state into cloud Claude Code sessions: storage and sync options

Subagent report, researched 2026-09-30, for the personal-cloud-environment design question
(see `../../2026-09-30-personal-cloud-env-research.md`). Written before the design settled on
the Mac mini as the always-on hub; its "hub VM" is therefore whichever machine holds the union
of state. The measurements in §1 were taken read-only on the laptop (host "SK").

## Bottom line

Don't mirror "the Mac" as one thing. Split the state by who writes it and how. Then:
- **Always-on hub.** One machine with the union of state on a snapshotting filesystem is the meeting point.
- **Transcripts.** Live-sync only the transcript window (`~/.claude/projects`) between hosts with a file syncer whose conflict mode only renames the loser.
- **Config.** Keep the git sync already running for authored config (`SSFSKIM/claude-config`, structural JSON merge). Trigger it on change instead of every 30 minutes.
- **Machine-bound state.** Keep runtime files local to each host, and broker secrets instead of copying files.
- **Versioning.** Snapshots on the hub, plus an offsite copy to B2 or R2.

The rule that keeps append-only files safe: **every transcript file has exactly one writing host.** Resuming a session on another host forks it (`--fork-session`), and the sync tool's conflict mode may only rename the losing copy, never overwrite it.

## 1. What is actually in ~/.claude on this Mac (measured 2026-09-30, read-only)

| Path | Size | Files | Class |
|---|---|---|---|
| `jobs/` | 20.3 GB | 326k | Scratch. One job's `tmp/` (`jobs/bb761c28/tmp`) is 20 GB. Host-local; exclude. |
| `projects/` | 13.0 GB | 55k | Transcripts. 805 project dirs; 3,272 top-level `.jsonl`; 7,179 subagent `.jsonl`; 6,666 tool-results files. |
| `plugins/` | 1.7 GB | 103k | Rebuildable from the manifest (`sync/apply.py`). |
| everything else | < 0.3 GB | — | Config, `history.jsonl` (4.2 MB), `~/.claude.json` (299 KB). |

What this changes about the problem:
- **The 30-day sweep is already running.** `cleanupPeriodDays` is unset, so the 30-day default applies. The oldest transcript's mtime is 2026-08-31, exactly 30 days ago. The 13 GB is a rolling window, and older history is already gone. [docs](https://code.claude.com/docs/en/claude-directory), [#85466: 950 transcripts deleted in one sweep](https://github.com/anthropics/claude-code/issues/85466).
- **Growth rate.** About 4.3 GB of transcript files were touched in the last 7 days, and 13 GB covers 30 days: roughly **0.43–0.6 GB/day**, or 157–220 GB/year uncompressed.
- **Compression.** zstd-3 on a 263 MB sample of recent transcripts gave **4.5×** whole-file and **4.2×** in 128 KiB chunks (about what ZFS would get per record).
- **Large files.** 56 transcripts are over 20 MB; the largest is 80 MB. This matters for tools that rebuild the whole file on each sync.
- **Existing sync.** `~/.claude` is already a whitelist git repo. The authored-config class is already solved except for latency.
- **What you're really mirroring** is about 13–15 GB and 55k files, not 35 GB.

## 2. State classes (by writer pattern)

- **T: per-session transcripts.** `projects/<key>/<uuid>.jsonl`, `<uuid>/subagents/`, `<uuid>/tool-results/`, `memory/`. One writer per file, append-mostly, UUID-named, so conflict-free by construction. Claude Code sometimes sets a transcript aside rather than overwriting it (`.superseded-*` / `.orphaned-*`), so "append-only" is not absolute. [docs](https://code.claude.com/docs/en/claude-directory)
- **H: shared logs appended by every host.** `history.jsonl` (every prompt, every session). Any file-level sync conflicts on it constantly.
- **C: small authored config.** `CLAUDE.md`, `settings.json`, skills, agents, hooks, keybindings. Rarely edited, occasionally by both sides.
- **L: host-local runtime.** `~/.claude.json` is rewritten whole, has a history of corruption under concurrent writers ([#28922](https://github.com/anthropics/claude-code/issues/28922)), and holds path-keyed trust and the account. `sessions/` holds live-session and crash detection; a new launch "clears crash leftovers", so syncing it would let one host's launch delete another host's live markers. Also local: `shell-snapshots/`, `session-env/`, `file-history/`, `jobs/`, `debug/`, `paste-cache/`, `backups/`, `.credentials.json`.
- **S: secrets and OS state not in the filesystem.** Keychain, TCC, launchd, the Chrome profile, `tailscaled` state.
- **R: git repos** under `~/Developer`.

## 3. Evaluation of the approaches

### A. Bidirectional sync daemons

| Tool | (a) One-side append | (b) Both sides append |
|---|---|---|
| Mutagen `two-way-safe` | rsync-style delta; staged and "atomically relocated" into place | Conflict is recorded and the file stops syncing until you delete the loser. Nothing lost, but it goes stale. |
| Mutagen `two-way-resolved` | same | **Alpha wins every conflict: beta's appended lines are overwritten**, and the docs say "no conflicts can occur". Never use it for T or H. |
| Syncthing | Fixed 128 KiB–16 MiB blocks from offset 0, so only the tail blocks travel. The receiver rebuilds a temp file and renames it over the original. | The copy with the older mtime becomes `<name>.sync-conflict-<date>-<device>`. Both survive; `maxConflicts` defaults to 10. |
| Unison | Transfer via temp file and rename | Conflict skipped in batch mode. `copyonconflict` + `prefer newer` keeps the losing copy; a `merge=` program can union-merge lines. |
| rclone bisync | Whole file per run (S3/R2 cannot append) | Default `--conflict-resolve none` renames both copies to `.conflict1` / `.conflict2`. |

Sources: [Mutagen modes](https://mutagen.io/documentation/synchronization/), [staging](https://mutagen.io/documentation/synchronization/staging/), [Syncthing syncing](https://docs.syncthing.net/users/syncing.html), [config](https://docs.syncthing.net/users/config.html), [Unison](https://man.archlinux.org/man/unison.1.en), [rclone bisync](https://rclone.org/bisync/).

**Mutagen.** On macOS it watches natively and recursively; on Linux it polls every 10 s by default plus native watches on recently changed files ([watching](https://mutagen.io/documentation/synchronization/watching/)). Scale: ~1 s per change at 42k files ([#100](https://github.com/mutagen-io/mutagen/issues/100), old version); a chained Mac→hub→VM hop took 20–30 s ([#551](https://github.com/mutagen-io/mutagen/issues/551), Jan 2026, no maintainer reply). Maintenance risk: last release v0.18.1 (Feb 2025); release binaries include SSPL-licensed code since v0.17; the MIT-only fork was abandoned Oct 2025 ([releases](https://github.com/mutagen-io/mutagen/releases), [fork](https://github.com/sagemathinc/mutagen-open-source)). Its own docs say don't sync `.git` ([VCS page](https://mutagen.io/documentation/synchronization/version-control-systems/)).

**Syncthing.** Latency: watcher waits 10 s by default (`fsWatcherDelayS`), deletes wait a further 1 minute; `fsWatcherTimeoutS` caps the delay for files that keep changing. A file being actively appended can defer with "modified but not rescanned" until it goes quiet ([forum](https://forum.syncthing.net/t/what-does-modified-but-not-rescanned-mean/11123)). Versioning only archives changes received from other devices ([versioning](https://docs.syncthing.net/users/versioning.html)). Send-only / receive-only folder types ([folder types](https://docs.syncthing.net/users/foldertypes.html)); `.stignore` supports `(?d)`, `!`, `#include` ([ignoring](https://docs.syncthing.net/users/ignoring.html)). Known scale risks: [#10894](https://github.com/syncthing/syncthing/issues/10894) (Sep 2026) — the macOS FSEvents watcher keeps every created path forever, 3.5 GB heap after 4 days on 665k files; UUID-named transcripts are exactly that churn pattern. [#10264](https://github.com/syncthing/syncthing/issues/10264) — the v2 SQLite database slowed badly around 60k files on v2.0.1; retest on the current release.

**Unison.** macOS needs a third-party fsmonitor for `-repeat watch` ([autozimu/unison-fsmonitor](https://github.com/autozimu/unison-fsmonitor)); each pair of machines needs its own process; its one strength is `merge=` for union-merging `history.jsonl`.

**rclone bisync.** A batch job, not live; re-uploads whole files to object storage every run; backstop only.

### B. Network filesystems

- **Serving from a laptop fails the "asleep or offline" requirement.** macOS `nfsd` serves only NFSv2/v3 ([NFS Manager](https://www.bresink.com/osx/NFSManager.html)). With `hard` mounts, client processes hang in D state while the server is gone; `soft` mounts "can cause silent data corruption" ([nfs(5)](https://man7.org/linux/man-pages/man5/nfs.5.html)). SSHFS was orphaned then revived (3.7.5). Taildrive is alpha, WebDAV-based, served by the sharing device itself ([docs](https://tailscale.com/docs/features/taildrive)).
- **Serving from the always-on hub is fine.** NFSv4 `hard` mounts over Tailscale; Linux attribute cache defaults acregmin 3 s / acregmax 60 s (`actimeo`).
- **Host-to-microVM sharing:** Firecracker has no virtio-fs or 9p upstream ([#1180](https://github.com/firecracker-microvm/firecracker/issues/1180)); only block devices. Cloud Hypervisor supports virtio-fs through `virtiofsd` with DAX disabled ([fs.md](https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/fs.md)). Apple's Virtualization framework has [`VZVirtioFileSystemDeviceConfiguration`](https://developer.apple.com/documentation/virtualization/vzvirtiofilesystemdeviceconfiguration) for VMs on the Mac itself.

### C. Object-storage-backed filesystems

**JuiceFS.** Passes all 8,813 pjdfstest tests; rename atomic ([README](https://github.com/juicedata/juicefs)). Close-to-open consistency with a 1 s attribute/entry cache ([cache](https://juicefs.com/docs/community/guide/cache/)). `juicefs clone` is a metadata-only redirect-on-write copy ([clone](https://juicefs.com/docs/community/guide/clone/)). Gaps: community edition has no snapshots, trash defaults to 1 day; hourly metadata backup auto-disabled past 1M files; metadata ~300 B/file (Redis) or 600 B/file (SQL); R2's ListObjects is unsorted, which breaks `gc`, `fsck`, `sync`, `destroy`; containers need `SYS_ADMIN` + `/dev/fuse`; macOS needs macFUSE (kext path requires Reduced Security; macFUSE 5 FSKit only mounts under `/Volumes`); every `open` queries the metadata engine, so a Mac mount is useless offline. Verdict: right only if sessions run on many ephemeral hosts that can't sit next to the hub.

**mountpoint-s3.** No append and no rename on general-purpose buckets; unusable for JSONL ([SEMANTICS](https://github.com/awslabs/mountpoint-s3/blob/main/doc/SEMANTICS.md)). **rclone mount.** Uploads after close + 5 s; caches directories 5 minutes; no coherency between hosts. **SeaweedFS.** Extra servers, FUSE only, no snapshots in OSS.

**Backing-store prices** (2026 third-party summaries): R2 $0.015/GB-month, $0 egress, $4.50 per million Class A ops, 10 GB free. B2 $6.95/TB-month since May 2026, API calls free, egress free up to 3× stored. Canonical: [R2](https://developers.cloudflare.com/r2/pricing/), [B2](https://www.backblaze.com/cloud-storage/pricing).

### D. Block volumes

- **Fly:** $0.15/GB-month; one volume per Machine; snapshots $0.08/GB-month (first 10 GB free), retention 5 days default, up to 60 (3P). [pricing](https://fly.io/docs/about/pricing/), [volumes](https://fly.io/docs/volumes/overview/)
- **Hetzner:** €0.0572/GB-month since Apr 2026; one server at a time; **no volume snapshots**. [product](https://www.hetzner.com/cloud/block-storage/), [FAQ](https://docs.hetzner.com/cloud/volumes/faq/)
- **EBS:** gp3 $0.08/GB-month; snapshots $0.05/GB-month incremental; Multi-Attach only io1/io2, no I/O fencing.
- **Consequence:** a volume can't be shared by concurrent sessions on different VMs. Use one as the hub's disk and do the sharing and copy-on-write above it.
- **ZFS:** snapshots and clones "nearly instantaneous", "initially consume no additional space" ([zfsconcepts](https://openzfs.github.io/openzfs-docs/man/master/7/zfsconcepts.7.html)). OpenZFS 2.2+ can be the overlayfs upper layer ([PR #14070](https://github.com/openzfs/zfs/pull/14070)). Compression is per record, so ratios come in below the `zstd` CLI; the measured 4.2× is the planning figure.

### E. Git

- **Good fit for config.** The existing whitelist repo with structural JSON merge beats any file syncer for a `settings.json` edited on both sides.
- **Dotfiles outside `~/.claude`:** chezmoi with OS templating (`.chezmoi.os`) and 1Password/age secret references ([chezmoi](https://www.chezmoi.io/user-guide/manage-machine-to-machine-differences/), [1Password](https://www.chezmoi.io/user-guide/password-managers/1password/)).
- **Bad fit for transcripts:** LFS stores every version whole ([git-lfs #5910](https://github.com/git-lfs/git-lfs/discussions/5910)); ordinary packs delta append-only files but the cost grows — an 18 MB append-only file produced a 1.6 GB repo and a 21-minute clone ([LWN](https://lwn.net/Articles/774125/)); ~55k files a month.
- **Repos:** git itself is the sync layer. Never live-sync `.git` between working trees.

### F. macOS specifics

- **APFS local snapshots** from `tmutil localsnapshot` disappear within ~24 hours ([Jamf thread](https://community.jamf.com/general-discussions-2/keep-local-apfs-snapshots-for-restore-snapshots-don-t-persist-20215)). An undo buffer, not a history layer.
- **FSEvents** coalesces events; on drops it sets `MustScanSubDirs` and the watcher must rescan ([Apple guide](https://developer.apple.com/library/archive/documentation/Darwin/Conceptual/FSEvents_ProgGuide/UsingtheFSEventsFramework/UsingtheFSEventsFramework.html)).
- **Not in the filesystem:** Claude Code's OAuth login (Keychain item `Claude Code-credentials`, [auth docs](https://code.claude.com/docs/en/authentication)); the gh token (Keychain `gh:github.com`, so a mirrored `hosts.yml` gives a broken login, [cli #7757](https://github.com/cli/cli/issues/7757)); ssh-agent/Keychain keys, TCC grants, launchd jobs, the Chrome profile and Playwright extension token.
- **`tailscaled` state must never be copied:** cloned node keys cause "duplicate node key" fights ([troubleshooting](https://tailscale.com/docs/reference/troubleshooting/network-configuration/multiple-devices-same-100.x-ip-address), [#506](https://github.com/tailscale/tailscale/issues/506)).

## 4. Recommended layered design

Topology: laptop ⇄ (Tailscale) ⇄ **hub** ⇄ sessions. GitHub carries config and repos. B2 or R2 holds the offsite copy.

| Class | Mechanism | Source of truth | Versioning |
|---|---|---|---|
| T: `~/.claude/projects` (includes `memory/`) | File sync, folder root = `projects/` only, each host ⇄ hub. Hub sessions write directly into it. | The writing host, per file. Hub = archive of record. | Hub snapshots + offsite copy |
| H: `history.jsonl` | Host-local (exclude). Optional nightly union-merge into an archive on the hub. | Each host | Hub snapshot of the archive |
| C: authored config | `claude-config` git repo. Trigger `sync.sh` from a filesystem watch with ~5 s debounce and from session start/stop hooks, instead of every 30 min. | Git remote | Git history + hub snapshots |
| Dotfiles outside `~/.claude` | chezmoi, templated per OS | Git remote | Git |
| Plugins | Rebuilt per host from the manifest (`apply.py`) | Manifest in git | Git |
| L: runtime files, `~/.claude.json`, `jobs/`, `file-history/` | Not mirrored. `~/.claude.json` seeded from a template plus `sync/mcp.json`. | Each host | None needed |
| S: secrets | Brokered | 1Password or a cloud secret manager, or the gateway | — |
| R: repos | Push/pull through GitHub or a bare mirror on the hub. WIP goes to `wip/<host>` branches. | Git remote | Git |

**Secrets, per session:** Claude: `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (~1 year, no auto-refresh; lacks the scope Remote Control needs, [#96076](https://github.com/anthropics/claude-code/issues/96076)) — or a gateway that holds the credential. GitHub: `GH_TOKEN` fine-grained PAT. SSH: forward the agent only while the laptop is awake; otherwise deploy keys or SSH certificates. Tailscale: an ephemeral, tagged, reusable auth key per sandbox ([ephemeral nodes](https://tailscale.com/docs/features/ephemeral-nodes)). launchd jobs become systemd timers via chezmoi.

**Per-session copy-on-write views (sessions on a ZFS hub), if ever wanted:** `zfs snapshot tank/home@s-$ID && zfs clone … tank/sess/$ID` takes milliseconds and 0 bytes; bind-mount `tank/claude/projects` read-write over the clone so transcripts are shared live; private per session: `~/.claude.json`, `sessions/`, `jobs/`, `file-history/`; at end, `zfs diff` and commit config changes through the git sync, destroy the clone. Alternative: overlayfs with the lower layer at `.zfs/snapshot/s-$ID` (OpenZFS ≥ 2.2).

**Guardrails (each maps to a real failure):**
1. **Set `cleanupPeriodDays` explicitly in user settings on every host before the first sync.** Any host starting with the default sweeps every project, and the deletions sync everywhere.
2. **Cross-host resume always uses `claude --resume <id> --fork-session`,** so no file ever has two writers. Resume by ID searches all projects since v2.1.223 but needs the file on the local machine ([sessions](https://code.claude.com/docs/en/agent-sdk/sessions)).
3. **Make paths identical.** On every host, `HOME=/Users/new` and repos under `/Users/new/Developer/...`. Fallback: `CLAUDE_CONFIG_DIR` + `CLAUDE_CODE_PROJECT_DIR_NAME` (v2.1.234+) ([env vars](https://code.claude.com/docs/en/env-vars)).
4. **Conflict policy only ever renames the loser.** Never `two-way-resolved`, Unison `prefer`, or `--conflict-loser delete` on T or H.
5. **Watch the Syncthing FSEvents leak (#10894) on macOS** if Syncthing is used: restart the daemon daily until a fix ships.
6. **Encrypt the hub pool / backups.** Transcripts contain whatever passed through the tools.
7. **SDK-driven headless agents:** `SessionStore` with the S3 adapter against R2 stores one part object per append and concatenates on load — conflict-free by construction; writes are best-effort (3 attempts, then dropped with `mirror_error`), so dedupe by `entry.uuid`. Not applicable to interactive CLI sessions ([session storage](https://code.claude.com/docs/en/agent-sdk/session-storage)).

## 5. Numbers

**Latency** (docs-based, not benchmarked):

| Path | Expected |
|---|---|
| Laptop ⇄ hub transcripts (Syncthing) | ~2–12 s: 10 s default watcher delay, tunable to 1–2 s, plus the Tailscale round-trip. Deletes add 60 s. A file being actively appended settles after the turn ends. |
| Laptop ⇄ hub transcripts (Mutagen) | ~1 s; 20–30 s on a chained hop |
| Session on hub → hub filesystem | Immediate (same kernel) |
| Remote sandbox via NFS | Close-to-open, then 3–60 s attribute cache |
| Config via triggered git | ~10–60 s (today: up to 30 min) |

**Storage** for a year of daily snapshots: transcripts at 0.43–0.6 GB/day = 157–220 GB/year uncompressed; at 4.2× that is **37–52 GB on disk**. Append-only files make snapshots nearly free (a snapshot pins only the rewritten tail record of files being appended at snapshot time; under ~1 GB/year). Full daily copies would be 13 GB × 365 ≈ 4.7 TB.

**Cost per month for a cloud hub** (if there is no home machine): Hetzner CAX11 €5.99 (CAX21 €10.49) + 100 GB volume €5.72 + offsite ~$0.3–0.5 ≈ **€12/month**. Fly: a 100 GB volume is $15/month and snapshots can't cover a year. EBS: gp3 100 GB $8/month plus $3–5/month of snapshots plus the instance.

## 6. Not verified / open

- Whether Syncthing's `copyRangeMethod` (copy_file_range or reflink) makes the temp-file rebuild cheap on OpenZFS 2.2+ block cloning or APFS; if not, each sync cycle rewrites the whole file on the receiver, up to 80 MB per sync of an active large transcript.
- Whether Syncthing's inotify watch on the hub sees writes arriving through the kernel NFS server.
- Whether Syncthing v2's scaling problem at ~60k files is fixed in the current release.
- Mutagen's check that the target hasn't changed between scan and apply.
- R2 and B2 prices came from 2026 third-party summaries; the Linux NFS attribute-cache defaults from memory of nfs(5).
- Anthropic-hosted Claude Code on the web doesn't read `~/.claude/skills` from any machine; only claude.ai-enabled skills sync, and only downward. The hub design applies to sessions you host yourself.
