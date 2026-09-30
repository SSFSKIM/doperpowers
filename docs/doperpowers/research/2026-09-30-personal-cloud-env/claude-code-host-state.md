# Host-state inventory for Claude Code 2.1.283

Subagent report, 2026-09-30, for the personal-cloud-environment design question
(see `../../2026-09-30-personal-cloud-env-research.md`). Read-only inspection of the extracted
bundle at `~/claude-code-bundle/2.1.283/cli.pretty.js` (cited as `cli:<line>`) and its spec
library `~/claude-code-bundle/2.1.283/SPEC/` (chapters A3, 03, 08, 35, 36, 37 most useful; ~40
citations spot-checked against the bundle). No secrets were printed: key names and shapes only.

**Headline.** Claude Code already has a working version of "run a session in a container as this person": the **self-hosted runner's host-config snapshot**. It copies the operator's `~/.claude` into each session, minus an explicit exclusion list (cli:993921, SPEC/37 §37.23.6). That list is the best available template for what should move and what should stay behind.

### A. Config roots and relocation
- **Config home.** `be = (CLAUDE_CONFIG_DIR ?? ~/.claude).normalize("NFC")` (cli:84458).
- **Global config file.** If `<configHome>/.config.json` exists it is used. Otherwise the file is `<CLAUDE_CONFIG_DIR or $HOME>/.claude<suffix>.json` (cli:1026145). When `CLAUDE_CONFIG_DIR` is set, `.claude.json` moves inside it.
- **Other environment variables that move state:**
  - `CLAUDE_SECURESTORAGE_CONFIG_DIR`: credentials directory (cli:658591).
  - `CLAUDE_CODE_PLUGIN_CACHE_DIR`: whole plugin home (cli:133034).
  - `CLAUDE_CODE_PLUGIN_SEED_DIR`: read-only plugin seed roots, `PATH`-separated (cli:133040).
  - `CLAUDE_CODE_PROJECT_DIR_NAME`: overrides the `projects/` key, but only when `CLAUDE_CONFIG_DIR` is also set (cli:84466, cli:983419).
  - `CLAUDE_CODE_REMOTE_MEMORY_DIR`: agent and auto-memory root (cli:55353).
  - `CLAUDE_CODE_TMPDIR`: temp root, default is literally `/tmp` (cli:578270).
  - `CLAUDE_CODE_TASK_LIST_ID`, `CLAUDE_DEV_MODS_DIR`.
  - `--project-config-root <dir>`: project settings, `.mcp.json` and `.claude/*` trees are read from `<dir>` instead of the working directory.
- **XDG.** Never used for Claude Code's own config. `XDG_DATA_HOME`/`XDG_STATE_HOME`/`XDG_CACHE_HOME`: install layout only (cli:710552-710563). `XDG_RUNTIME_DIR`: messaging sockets (cli:589777). `XDG_CONFIG_HOME`: only the global git ignore file (cli:242465) and the `~/.config/anthropic` profile store.
- **Paths hard-wired to the home directory, not the config home:** `bridge-spawn` (cli:312335), `~/.claude/state/settings-review.json` (cli:979590), `unattended-serving-consent.json`.
- **What lives where:**
  - `~/.claude/settings.json`: user settings — permissions, hooks, env, `enabledPlugins`, model.
  - `~/.claude.json`: account and machine state — `oauthAccount`, `userID`, `machineID`, `anonymousId`, user-scope `mcpServers`, GrowthBook caches, onboarding flags, and `projects["<absolute cwd>"]` (trust, `allowedTools`, local-scope `mcpServers`, last-session metrics).
  - `<cwd>/.claude/settings.json`: shared project settings; `.claude/settings.local.json`: read at the canonical git root when that root, its `.git` and any `.claude` entry are owned by the current user; otherwise at the working directory.
- **Settings precedence, lowest first:** `["userSettings","projectSettings","localSettings","flagSettings","policySettings"]` (cli:685358). Plugin base settings sit underneath all of them. The policy tier is server-managed `remote-settings.json`, MDM plists, `/Library/Application Support/ClaudeCode/managed-settings.json` plus `.d/` (SPEC/03 §5).

### B. Credentials
- **macOS: login keychain.** `security find-generic-password -a "$USER" -w -s "Claude Code-credentials"` (cli:74906). With a non-default `CLAUDE_CONFIG_DIR` the service name gains `-<sha256(dir)[:8]>` (cli:658597). Backend "keychain-with-plaintext-fallback" (cli:74847). Confirmed on this Mac: the item exists in `login.keychain-db`.
- **Linux: plaintext file** `<config home>/.credentials.json`, mode 0600 (cli:312397). No libsecret/gnome-keyring/kwallet backend (SPEC/A3 §A3.8). This Mac's `.credentials.json` holds only `mcpOAuth`.
- **Credential shape:** `{claudeAiOauth:{accessToken, refreshToken, expiresAt, scopes, subscriptionType, rateLimitTier}, designOauth?, enterpriseGateway?, mcpOAuth?, organizationUuid?, trustedDeviceToken?}` (SPEC/08 §8.5).
- **Bearer-token selection order** (cli:58930): bare mode → `ANTHROPIC_AUTH_TOKEN` → `CLAUDE_CODE_OAUTH_TOKEN` → fd-handed token or `/home/claude/.claude/remote/.oauth_token` (cli:819305) → `apiKeyHelper` → Workload Identity Federation → stored claude.ai credential. `ANTHROPIC_API_KEY` is used headless without the approval prompt.
- **`claude setup-token`** issues a 365-day, **inference-only** token that is printed and never stored (cli:153917). Because it is inference-only, Remote Control refuses it (SPEC/08 §15).
- **Other host hand-over paths:** `CLAUDE_CODE_HOST_CREDS_FILE` (0600, owner-checked, pid-bound, requires `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`), `CLAUDE_BG_AUTH_SNAPSHOT_PATH` (one-shot), `*_FILE_DESCRIPTOR` env vars, the SDK `oauth_token_refresh` control request.
- **Refresh.** Serialised by `<credentials dir>/.oauth_refresh.lock`. On `invalid_grant` the refresh token is marked dead and overwritten with `refreshToken:""` (SPEC/08 §6.7). **Copying one refresh token to two machines makes them race; whichever refreshes second is logged out.** There is no cross-machine credential sync.
- **This user's inference path does not go through claude.ai OAuth directly:** `settings.json` `env` sets `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL=http://127.0.0.1:8641`, a local gateway (claude-usage-menubar's ClaudeUsage.app). A container cannot reach it as configured.

### C. Session storage
- **Transcript path:** `projects/<key>/<sessionId>.jsonl`. The key is the working-directory path with every character outside `[A-Za-z0-9]` replaced by `-`; past 200 characters it is truncated and a hash suffix added (cli:117241-117246). No lower-casing.
- **Appends:** `appendFileSync(path, JSON+"\n", {mode:0o600})` (cli:967453), no fsync. Each append also fires the SDK mirror.
- **Mostly append-only.** Three writers rewrite the file: (1) tombstone removal on rewind/retract — in-place truncate-and-rewrite, with a whole-file rewrite fallback (cli:964893); (2) local GC via temp+rename, gated `CLAUDE_CODE_TRANSCRIPT_LOCAL_GC` / `tengu_transcript_local_gc`, **off by default** (cli:256933); (3) cloud-session hydration replaces the whole transcript (cli:966752).
- **Compaction does not rewrite.** It appends a `compact_boundary` record; the loader discards everything before an unpreserved boundary (SPEC/35 §35.5.13).
- **Per-session artefacts:** `<sid>/subagents/agent-*.jsonl` + `.meta.json`; `<sid>/tool-results/*` (spilled outputs, referenced by absolute path from the transcript); `<sid>/custom-title.json`, `ccr-tip.json`, `precompact.json`; `file-history/<sid>/<16hex>@v<N>` (cli:970902); `session-env/<sid>/*-hook-N.sh`; `shell-snapshots/snapshot-<shell>-<ms>-<rand>.sh` (cli:882706); `tasks/<listId = sessionId>/`, `plans/<slug>.md`, `debug/<sid>.txt`, `telemetry/1p_failed_events.*`; `sessions/<pid>.json` + `.key` (live-process registry); `history.jsonl` (prompt history).
- **Legacy, prune-only:** `todos/`, `statsig/`, `logs/`, `access-audit/` (cli:312350). `.session-stats.json` has no code path.
- **No sqlite and no session index.** `/resume` lists sessions by reading the head and tail of each JSONL.
- **Paths are baked into records:** each record carries `cwd` and `gitBranch`; file-history records carry absolute `trackingPath`s.

### D. Remote and cloud mechanisms that already exist
1. **Cloud sessions.** `--cloud [description|session_id|url]` (`--remote` deprecated alias), `--environment <ccpool_…>` for self-hosted runners (cli:71126). Sessions are REST resources at `api.anthropic.com/v1/code/sessions/<cse_…>`; events over SSE at `/worker/events/stream`, written by POST to `/worker/events`; status `PUT /worker` (cli:257358, 715553). Repo seeding: git clone, uploaded git bundle, or folder seed. Optional two-way directory sync ships files as `synced_file` rows; hidden files and `node_modules` never uploaded (SPEC/37 §37.18). Container env: `CLAUDE_CODE_REMOTE=true`, `CLAUDE_CODE_OAUTH_TOKEN=<inference token>`, synced root `/mnt/user-data/working`.
2. **Laptop → cloud: `/teleport`.** Posts to `/v1/code/sessions/<id>/move-to-cloud` (cli:718004). Needs an active Remote Control bridge, a claude.ai login, a clean and pushed git tree, and a managed environment; branch `claude/teleport-<id[-8:]>`. Menu behind `tengu_teleport_send_to_cloud`, **default false**. Cloud → laptop is `claude --teleport <id>` (fetches the transcript, checks out the branch).
3. **Phone or web drives the local session: Remote Control.** `claude remote-control` (alias `rc`, cli:71342), `/remote-control`, `/mobile`, `--remote-control`, and `remoteControlAtStartup` (**true in this user's config**). The laptop is the worker; phone and laptop never connect directly; everything relays through the session record. The headless server registers with `POST /v1/environments/bridge` (cli:429394) and spawns `claude --print` children; `~/.claude/bridge-spawn/<id>-XXXXXX/{mcp.json, append-system-prompt.txt}` is that per-child staging. `autoUploadSessions` is dead in this build.
4. **Cloud agent runs tools on the laptop: remote tool serving.** Uses the device bridge; the laptop publishes a `HostDescription` and a set of served tools (this harness's own tool names, routed per call by a `_host` argument); consent in `~/.claude/state/unattended-serving-consent.json` (SPEC/37 §37.19). Behind `tengu_violin_wood` (default false) with an emergency mute `tengu_violin_mute`. Not in public docs as of 2026-09-30.
5. **Sending this machine's config to cloud sessions.** Settings "home seed" (`--forward-home-settings`): consumer exists, producer is a stub `async function N2o(...) { return; }` (cli:937956) — **not live**. `/cloud-plugins` sends plugin names and marketplace addresses, never files (consent keyed to hostname, cli:415364). Hook forwarding: hooks run on the laptop for the cloud session; scripts inside the checkout are refused. Account skills and plugins sync *down* from claude.ai into `skills/synced` / `plugins/synced`; nothing syncs local user skills up. All behind `tengu_violin_*` flags.
6. **Self-hosted runner.** Snapshots `SELF_HOSTED_RUNNER_HOST_CONFIG_DIR || CLAUDE_CONFIG_DIR || ~/.claude` (cli:993988), `--host-config-snapshot disk|memory` (memory capped at 64 MiB). **Excluded from the copy:** `.claude.json`, `.credentials.json`, `projects`, `sessions`, `todos`, `shell-snapshots`, `statsig`, `file-history`, `history.jsonl`, `ide`, `logs`, `backups`, `daemon`, `jobs`, `teams`, `state`, `plans`, `telemetry`, `debug`, `cache`, `tasks`, `session-env`, `bridge-spawn`, `paste-cache`, `chrome`, `downloads`, `seed-admin`, … plus every dotfile and every name starting `daemon` or `agent-memory` (cli:993921, 993978). Each session child gets its own `CLAUDE_CONFIG_DIR` under `<base-dir>/_sessions/`, kept unless `--remove-session-state`. Pool sessions are never device-bound and never sync files. Docs (2026-09-30): public beta on **Team and Enterprise** only; inference cannot go through an LLM gateway; the docs point Pro/Max users at Remote Control for "your own always-on machine".
7. **Agent SDK `SessionStore`** (`agent-sdk-0.3.259/sdk.d.ts:5528`): `append(key, entries)` after each local write (batched ~100 ms), `load(key)` materialised to a temp JSONL for resume; `uuid` is the idempotency key. Ready-made transcript portability for SDK-driven sessions only.
8. **Chrome relay.** Claude in Chrome can pair across machines through `wss://bridge.claudeusercontent.com/chrome/<userId>` (cli:488119, SPEC/46 §46.5).

### E. Plugins and skills
- **Plugin home:** `CLAUDE_CODE_PLUGIN_CACHE_DIR` or `<config home>/plugins` (cli:133034). Registries `installed_plugins.json` (v2, absolute `installPath`, `projectPath`) and `known_marketplaces.json` (absolute `installLocation`). Cache layout `cache/<marketplace>/<plugin>/<version>/` (SPEC/30 §6.8); also `marketplaces/<name>/`, `data/<plugin>-<marketplace>/`, `asset-cache/`.
- **Portability:** new in 2.1.283, every `installPath`/`installLocation` is re-based under the current plugin home on load (SPEC/30 §9.1, cli:869768), so the cache survives a `$HOME` change. Project-scope installs are keyed by `projectPath` (not re-based). Alternative: `CLAUDE_CODE_PLUGIN_SEED_DIR`.
- **Skills load from:** `~/.claude/skills/<name>/SKILL.md`, `<cwd>/.claude/skills`, plugins, `/Library/Application Support/ClaudeCode/.claude/skills` (policy), `skills/synced` (claude.ai), and built-ins materialised to `/tmp/claude-<uid>/bundled-skills/`.
- **Plugins enabled here:** designer, doperpowers, eli5, ptc, pyright-lsp, swift-lsp, typescript-lsp.

### F. MCP servers
- Scopes (SPEC/31 §3.1): enterprise `managed-mcp.json`; managed `managedMcpServers`; project `.mcp.json` (walks up from cwd); user `~/.claude.json` top-level `mcpServers`; local `~/.claude.json` `projects["<cwd>"].mcpServers` (path-keyed); runtime-only `--mcp-config`, plugin-provided, claude.ai connectors (account-level, portable), agent frontmatter. MCP OAuth tokens live in the credential store under `mcpOAuth`.
- **Tied to this machine:** `cua_repl` (user scope; `node ~/.claude/tools/cua-shim.mjs`, drives the macOS GUI), `codex_computer_use` (local scope, one project), Claude-in-Chrome / Playwright extension (`PLAYWRIGHT_MCP_EXTENSION_TOKEN`, logged-in Chrome profile), the `swift-lsp` plugin (Xcode `sourcekit-lsp`).
- **Portable:** `openaiDeveloperDocs` (HTTP) and `ptc` (needs Python).

### G. Assumptions that only hold on macOS
- Keychain via the `security` CLI (exit 36 = locked keychain). Sandbox: `/usr/bin/sandbox-exec -p <profile>` on macOS (cli:311134) vs bubblewrap + seccomp on Linux. TCC identity: a synthesised `$XDG_DATA_HOME/claude/ClaudeCode.app` whose binary is a hard link to the executable so privacy grants survive updates (cli:839115); grants: computer-use and microphone. `osascript` for the daemon's re-auth notification (cli:572227), iTerm/Terminal deep links (cli:709723, 666183), clipboard image copy (cli:779649). Also `pbcopy`, `lsregister`, `afplay`, `~/Library/LaunchAgents/com.anthropic.claude-daemon.plist`, MDM plists. Computer use relies on `computer-use-swift.node` and `computer-use-input.node`.
- **This user's own hooks:** `hooks/claude-notify.sh` (osascript + terminal-notifier) and `notify.sh` (osascript). `~/.claude/chrome/chrome-native-host` is a wrapper pinned to a stale version (2.1.232).

### H. Compaction and resume
- **Resuming by UUID** finds `<sid>.jsonl` under any project key: override → matching project dirs → git worktree sweep → full scan of `projects/*`, refusing if two directories match (SPEC/35 §35.12.5). **The JSONL alone is enough to resume.**
- **Fidelity-only files:** `<sid>/subagents/*`, `<sid>/tool-results/*` (absolute paths from the transcript), `file-history/<sid>/` (only `/rewind`; resume copies it to the new id, cli:971260), `tasks/<sid>/`, `plans/<slug>.md`, the bound worktree path (missing → resume aborts or continues without isolation). Recreated on demand: `session-env`, `shell-snapshots`. Not needed: `sessions/<pid>.json`, `.ccr-tip.json`.
- **Compaction** adds a `compact_boundary` record plus a `precompact.json` sidecar; earlier records are never rewritten.

### Unusual directories in `~/.claude`
| Directory | Owner | What it is |
|---|---|---|
| `agora` | user tooling | Symlink to `sminos` (`orchestrating-daemons` → `agora`). Doperpowers sminos seat registry. |
| `bridge-spawn` | Claude Code | Remote Control headless server's per-child staging; currently empty. |
| `cc-daemon` | residue | Empty `sessions/` from June; the live daemon socket is `/tmp/cc-daemon-<uid>/…`. |
| `ccx` | user tooling | `roster/`, `run/`, `history.jsonl`, `prefs.json`; 0 hits in the bundle. |
| `channels` | channel plugin | `fakechat/outbox`. |
| `chrome` | Claude Code | Claude-in-Chrome native-messaging host wrapper. |
| `clock` | user tooling | `state.json` phase scheduler and `tick.jsonl`. |
| `daemon` | Claude Code | Background daemon state: `roster.json`, `dispatch/`, `auth/`, `control.key`, `attach-journal`. |
| `kairos` | doperpowers | Kairos-mode flag files, one per session id. |
| `sync` | user tooling | The git-based config sync (claude-config) run by launchd. |

### Minimum state a container needs to act as this user
1. **Inference auth.** `CLAUDE_CODE_OAUTH_TOKEN` from `setup-token` (inference-only, blocks Remote Control), or a `.credentials.json` holding `claudeAiOauth` (only safe if no other machine refreshes it), or — this user's actual path — the gateway: `ANTHROPIC_AUTH_TOKEN` + a reachable `ANTHROPIC_BASE_URL`.
2. **`~/.claude` minus the runner's exclusion set:** `settings.json`, `CLAUDE.md`, `rules/`, `agents/`, `commands/`, `skills/`, `output-styles/`, `hooks/`, `workflows/`, `keybindings.json`, the statusline script.
3. **Plugins:** `known_marketplaces.json`, `installed_plugins.json` and `cache/` (re-based on load), or `CLAUDE_CODE_PLUGIN_SEED_DIR`, or reinstall from the marketplaces.
4. **A curated subset of `~/.claude.json`:** `oauthAccount`, `userID`, user-scope `mcpServers`, and `projects["<path>"]` (trust, `allowedTools`, local MCP). Everything path-keyed means **keeping identical absolute workspace paths**, or setting `CLAUDE_CONFIG_DIR` plus `CLAUDE_CODE_PROJECT_DIR_NAME`.
5. **For continuity:** `projects/<key>/` (transcripts and `memory/`), `file-history/`, `tasks/`, `plans/`.

### State that cannot leave the Mac
- The login-keychain item `Claude Code-credentials` (export deliberately as a token instead).
- The local gateway at `127.0.0.1:8641` (reachable elsewhere only through a tailnet forward).
- `cua_repl` and computer use (macOS GUI, TCC-bound app identity).
- Claude-in-Chrome and the Playwright extension on the logged-in Chrome profile.
- osascript / terminal-notifier hooks, voice capture, swift-lsp/Xcode.
- The launchd daemon, `/tmp/cc-daemon-*` and `cc-socks` sockets, `sessions/<pid>` and `jobs/` registries.
