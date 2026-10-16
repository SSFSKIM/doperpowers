# devcloud — a cloud host that works like your Mac, on any substrate

**Date.** 2026-10-15. **Status.** Design approved in conversation; executing. **Prior art, reference
only.** `docs/doperpowers/specs/2026-10-02-personal-cloud-env-design.md` (the discarded devbox spec)
and its research under `docs/doperpowers/research/2026-09-30-personal-cloud-env/`;
`infra/worker-host/` (body / soul / seeding).

## Purpose

A person who runs Claude Code on two Macs wants more compute without a different way of working.
After this work, any Linux userland — a cloud VM, a Firecracker-style microVM, or a container on
one of those — becomes, by running one boot program, a host on which Claude Code behaves as it
does on the Macs: the same home path, the same `~/.claude` configuration (received from its git
repository, never pushed back), the same credentials on disk (from Google Cloud Secret Manager),
model inference through the person's own gateway on their tailnet, transcripts mirrored live to
their central session store, sminos membership on persistent hosts, and each project's checkout
prepared by that project's own `devenv/` scripts. Provisioning drivers that create the machines
(Hetzner, Vultr, GCE, Docker, Firecracker) are out of scope: this initiative builds the setup
system they will all call, and proves it on one container and one throwaway VM.

Alongside it, one guardrail the same hosts need: a mod that keeps secrets out of what the model
reads. The person's `/secret` mod (now in the `cua` plugin) refuses any command that touches its
store — too strict for daily use — yet knows only the values stored through it, so tokens in
other files (a proxy config, a shell rc) reached model context twice in the session that produced
this design. It moves into doperpowers and changes from deny to redact.

How to see it working: on a fresh container started from the devcloud image with a boot
descriptor and one seed credential, `claude -p "reply ok"` answers through the gateway, `gh` and
`gcloud` are authenticated, the run's transcript appears in the session store, and the project's
`devenv/setup.sh` has run — with no step typed by hand.

## Progress

- [x] (2026-10-15) Design approved in conversation; spec written.
- [ ] Independent spec review folded.
- [ ] M1 — Secrets guardrail mod in doperpowers; cua's copy retired.
- [ ] M2 — devcloud core: image, boot program, secrets materializer, pull-only config, services.
- [ ] M3 — The person's profile and Linux compatibility in their config repository.
- [ ] M4 — Project environments: the `devenv/` convention, its runner, its authoring skill.
- [ ] M5 — sminos on devcloud hosts, and acceptance on a container and a throwaway VM.

## Terms

- **Host**: a Linux userland devcloud has booted — VM, microVM, or container.
- **Substrate**: what the host runs on (VM, microVM, container). Only three things differ by
  substrate; everything else is shared (see Design §1).
- **Role**: `persistent` (long-lived, always-on, a sminos machine) or `sandbox` (minutes to
  hours, one task, discarded).
- **Boot descriptor**: `/etc/devcloud/boot.env`, the only per-host input a driver supplies.
- **Profile**: the person's private settings for devcloud, kept in their config repository at
  `~/.claude/devcloud/` (Design §3). doperpowers is public; nothing personal lives in it.
- **Seed credential**: the one credential a host needs before it can fetch anything else — a
  Secret Manager read-only service-account key file, or the GCE metadata server.
- **Gateway**: the person's model relay (a separate app) reachable on their tailnet; Claude Code
  reaches it through `ANTHROPIC_BASE_URL`. It holds every model credential; hosts hold none.
- **Session store**: the person's transcript mirror (`session-mirror`, a tool in their config
  repository's `tools/`), a Postgres reached over the tailnet; a host ships to it with
  `session-mirror ship`.
- **Mod**: a Claude Code function hook module (`hooks/mods/*.tsx`), loaded under
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`; see the repo map in `CLAUDE.md`.

## Acceptance

Each check names who runs it and what they observe. `<img>` is the image M2 builds; the boot
descriptor and seed are prepared as M5's Concrete Steps show.

1. **Redaction, not refusal (Mac).** In a session with the mod: `cat ~/.config/claude-secrets/K`
   for a stored key runs (no refusal) and the model sees `[secret:K]`. Printing a scratch file that
   holds a made-up `ghp_…` token shows a `[redacted:github-pat#1]` placeholder, in a subagent as in
   the main loop. The session's transcript file holds no raw value (`grep -c <value> <transcript>` is 0).
2. **Placeholders restore on write.** The model edits a file that holds a token it saw as a
   placeholder (an Edit whose `old_string` and `new_string` carry the placeholder); the file on
   disk still holds the real token afterwards, byte for byte. `ls`, `mv`, `test -f`, and writing a
   new file in `~/.config/claude-secrets/` all run.
3. **One boot, a working host (container).** `docker run` of `<img>` with a boot descriptor
   (`DEVCLOUD_KIND=container`, `DEVCLOUD_ROLE=sandbox`, one project) and the seed key mounted:
   within 5 minutes `devcloud status` reports every step `ok`; inside it, `claude -p "reply ok"`
   prints `ok` through the gateway; `gh auth status` and `gcloud auth list` show the expected
   identities; `session-mirror ls` on a Mac lists the run's session under the container's host
   name; the project's `devenv/setup.sh` ran (its marker or output present).
4. **Same on a VM, with systemd.** On a throwaway Ubuntu 24.04 VM given the same image recipe and
   a descriptor with `DEVCLOUD_KIND=vm`, `DEVCLOUD_ROLE=persistent`: check 3's observations hold;
   `systemctl status` shows the devcloud services active; after `sudo reboot` they come back and
   `devcloud status` is all `ok` again.
5. **Receive-only configuration.** On the VM, edit `~/.claude/settings.json`, then run the config
   pull job: the edit is gone and `git -C ~/.claude status --porcelain` lists no tracked change;
   `git -C ~/.claude push` fails.
6. **Credential-free image.** The built image contains no secret: the M1 detector run over its
   filesystem (and `docker history`) finds nothing, and `/etc/devcloud/boot.env` is absent from it.
7. **sminos on a persistent host.** On the VM, `devcloud` installs the sminos daemon as a systemd
   user unit when the host is enrolled (enrollment stays a human step); unenrolled, sminos runs
   local-only and `sminos chat` works in a project checkout. A sandbox never carries
   `$SMINOS_HOME/daemon/`, its hostname is unique, and its `DAEMON_BOOT_ID` differs from the
   host's.
8. **A repository describes its own environment.** `devenv up <name>` on a Mac or a host clones
   the repository and runs its `devenv/setup.sh`; re-running it with nothing changed does not
   reinstall. The authoring skill, pointed at a repository without `devenv/`, writes scripts that
   pass check 3 for that repository.

## Design

### 1. Substrate-agnostic by construction

Everything a host needs is one program, `devcloud-boot`, run as root at every boot. It reads one
input, the boot descriptor, and it is idempotent: running it again converges, never duplicates.
Three things differ by substrate, and each is a small adapter, not a fork of the logic:

| Varies | VM | microVM | container |
|---|---|---|---|
| How the image is produced | `image/setup.sh` on a builder, then a snapshot | `image/setup.sh` into a rootfs | `image/Dockerfile`, whose one build step is `image/setup.sh` |
| How the descriptor and seed arrive | cloud-init writes them | a metadata service or kernel argument writes them | a bind mount (descriptor, seed) |
| What runs the services | systemd | systemd | `devcloud-services`, a small supervisor, as the entrypoint's foreground after boot |

`devcloud-services` is chosen at runtime: when PID 1 is systemd, the boot program installs units;
otherwise the container entrypoint (`devcloud-boot && exec devcloud-services`) supervises the same
service list itself. One list, two runners — the alternative, requiring systemd in every
container (Sysbox can provide it), was rejected because it forces a runtime choice on every
container driver.

Tailscale also varies: a VM or microVM joins the tailnet itself (`DEVCLOUD_TAILSCALE=join`, with a
one-time, short-lived, tagged auth key the driver supplies in a file that the boot program
deletes after use); a container uses its host's tailnet through the host's routing
(`DEVCLOUD_TAILSCALE=host`). A sandbox never joins the tailnet as its own node: the free
Tailscale plan bounds short-lived tagged nodes to 1,000 node-minutes a month (enforcement
announced), which per-sandbox joins would exhaust in days.

### 2. The image: tools, never credentials

`devcloud/image/setup.sh` (run as root on Ubuntu 24.04) installs everything that is the same on
every host: git, build tools, Python 3.12 with venv, uv, Node LTS, jq, tmux, mosh, gh, the Google
Cloud CLI, hcloud, Tailscale, Docker client, and Claude Code (native installer, as the user). It
creates the user `new` with uid 501 and home `/Users/new` — the Macs' account. The home path is
not cosmetic: transcripts record working directories, the session store keys sessions by project
directory names derived from them, and the person's tools (`devenv`, `secret-env`, the statusline,
the trust template) hard-code `/Users/new`; with the same path a session started on a Mac resumes
on a host and back. `/Users` is a plain directory on Linux.

The image carries no credential, no boot descriptor, no `~/.claude` checkout, and no
`$SMINOS_HOME/daemon/`: a cloned enrollment would make two machines share one sminos identity
(their streams evict each other and their writers collide), and a cloned credential cannot be
revoked per host. Check 6 enforces this.

### 3. Public mechanism, private profile

doperpowers is a public repository, so `devcloud/` holds only mechanism. Everything personal lives
in the person's private config repository (cloned to `~/.claude` on every host), under
`~/.claude/devcloud/`:

- `profile.env` — shell-style `KEY=value` lines: the gateway URL and its non-secret marker token,
  the Secret Manager project, the session store host name convention, time zone and locale, extra
  `PATH` entries, and any environment the person wants on every host (Design §6).
- `secrets.toml` — what to fetch from Secret Manager and where to put it (Interfaces §I3).

The boot descriptor carries just enough to reach the profile: the config repository's URL, the
Secret Manager project, and the name of the secret holding the GitHub token used to clone it.

### 4. Boot sequence

`devcloud-boot` runs these steps in order, each recorded in `/var/lib/devcloud/status.json`
(`devcloud status` prints it). A step's failure stops the boot with the step named; the next run
retries from the top.

1. **Identity.** Set the hostname to `DEVCLOUD_NAME`; write `SESSION_MIRROR_HOST` and, for a
   container (which sees its host's boot id), a fresh `DAEMON_BOOT_ID` into the host environment
   file. Sandbox names must be unique; drivers use `sbx-<random>`.
2. **Network.** Join the tailnet when `DEVCLOUD_TAILSCALE=join` (auth key from the file, file
   deleted), else verify the gateway answers through the host's route.
3. **Seed.** Load the seed credential (`DEVCLOUD_SEED=file:<path>` or `gce-metadata`).
4. **Bootstrap secret.** Fetch the GitHub token named by `DEVCLOUD_CONFIG_TOKEN_SECRET`.
5. **Configuration.** Clone (or fetch and reset) the config repository into `~/.claude` as the user
   (Design §5), then read the profile.
6. **Secrets.** Materialize every entry of `secrets.toml` (Interfaces §I3).
7. **Apply.** Run the config repository's `sync/apply.py` (plugins, marketplaces, MCP servers,
   `~/.claude.json` seeding) as the user.
8. **Managed settings.** Write `/etc/claude-code/managed-settings.json` from the profile (Design §6).
9. **Services.** Install or start: the config pull job, the secrets refresh job, and the session
   store shipper (`session-mirror ship`); on a persistent host, the sminos daemon (Design §8).
10. **Projects.** For each `DEVCLOUD_PROJECTS` entry, `devenv up` (Design §7).

Steps 7 and 10 may run concurrently once step 6 is done — dependency installation dominates boot
time and needs nothing from step 7.

### 5. Configuration is received, never sent

A host keeps `~/.claude` as a clone it only receives: the pull job runs `git fetch` then
`git reset --hard origin/<branch>` every 30 minutes, and the clone's push URL is set to an
invalid value so a push fails loudly. A change made on a host — a model pick saved into
`settings.json`, a permission rule — lasts until the next pull, by design: configuration is
authored on the Macs. Machine-local differences live only where git does not reach: managed
settings (Design §6) and untracked files. The config repository's existing Linux sync unit
(`sync/claude-config-sync.{service,timer}`, `sync/install-systemd.sh`) commits and pushes; it is
removed in M3, because a pushing Linux host contradicts this rule.

### 6. Environment: three places, by who reads it

Processes on a host are not all started by a login shell — `claude --bg` sessions are started by
Claude Code's own daemon, services by systemd or `devcloud-services` — so a variable set only in a
shell rc reaches some of them and not others. Each setting goes where every reader sees it:

- **Claude Code settings** go in `/etc/claude-code/managed-settings.json`, which every session
  reads however it started: `ANTHROPIC_BASE_URL` (the gateway) and its marker token; the gateway's
  feature switches (`ENABLE_TOOL_SEARCH`, `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING`,
  `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`), pinned because the gateway's desktop app removes
  them from the synced `settings.json` when it quits; and empty values for Mac-only settings the
  synced file carries (a browser-extension token, `CLAUDE_CODE_PLUGIN_DIRS` pointing at an
  untracked directory).
- **Credentials** go in files (gh's `hosts.yml`, gcloud's active account and application default
  credentials, hcloud's `cli.toml`, `~/.pgpass`, MCP configs), which every process reads whatever
  its environment.
- **Everything else** goes in one environment file, `/etc/devcloud/env`, sourced by
  `/etc/profile.d/devcloud.sh` for shells and named as `EnvironmentFile` (or loaded by
  `devcloud-services`) for services: `PATH`, `LANG`/`LC_ALL`, `TZ`, the identity variables from
  boot step 1, the profile's extra variables, and the `env` targets of `secrets.toml`.

Project-specific environment belongs to the project's `devenv/` (Design §7).

### 7. Projects describe their own environment: `devenv/`

A repository that wants to run on a host carries a `devenv/` directory at its root (contract in
Interfaces §I4): `setup.sh` installs its dependencies and is safe to re-run; `start.sh`, optional,
starts its services; `env`, optional, names its environment and the Secret Manager secrets it
needs. The person's `devenv` tool (in their config repository, `tools/devenv`) becomes the runner:
`devenv up <name>` clones or fetches the repository, materializes its secrets, and runs
`devenv/setup.sh` when the repository changed since the last successful run. It replaces the
tool's earlier JSON manifest (`.devbox/environment.json`), which no repository adopted, so the
switch migrates nothing; scripts won because a repository's owner can express any install in a
script, while the manifest needed a schema for every case. A doperpowers skill teaches an agent to
write `devenv/` for a repository (M4).

Sandboxes start from a bare mirror their persistent host keeps per repository
(`/srv/devcloud/mirrors/<owner>/<repo>.git`, refreshed by the host), cloning with `--reference`
so a checkout takes seconds.

### 8. sminos on hosts

sminos 7.159.0 made Linux a first-class sminos machine: `sminos daemon install` writes a systemd
user unit. A **persistent** host is a sminos machine: enrolled once by the person
(`sminos hub enroll`, which takes a code made in their browser — deliberately a human step, since
the code carries the organization's key), after which boot step 9 runs `sminos daemon install`,
enables lingering for the user, and starts the unit. Unenrolled, the host's projects run
local-only. A **sandbox** is not a sminos machine: enrolling one would need the organization key
inside it and would leave its members on the desk as idle ghosts after it vanishes. Its sessions
are recorded by the session store instead, and whoever launched the sandbox (a seat on its host,
or the person) owns its outcome. Giving sandboxes their own short-lived identities is a hub
change, deferred (Out of scope).

### 9. The secrets guardrail mod

`hooks/mods/secrets.tsx` in doperpowers replaces `hooks/mods/secrets.tsx` in the `cua` plugin
(repository `~/Developer/GitHub/cua`). It keeps everything a person relies on today: the `/secret
[-g] KEY` command and its masked entry pane, the store layout and tiers
(`~/.config/claude-secrets/KEY` global, `~/.config/claude-secrets/projects/<slug>/KEY` per project,
mode 0600 files in a 0700 directory, the slug rule and the reserved `CUA_DEVICE_*` keys in the
global tier, as `cua`'s `src/secrets/store.mjs` documents), and the system-prompt section listing
the stored keys and how to use one (`"$(cat ~/.config/claude-secrets/KEY)"`). `cua` keeps its own
store library for its device credentials; only the mod moves.

Four changes:

1. **Redact, never refuse.** No tool call is denied for touching the store. Values are replaced in
   what the model and the transcript receive — the tool's result as the model reads it, the tool's
   own record (`toolUseResult`), and every appended row — before it leaves the process, so neither
   the model API nor the transcript file sees them. Refusal bought nothing redaction does not: a
   command that prints a value is caught at its output, and refusing reads also refused writes,
   moves, and existence checks.
2. **Known values from three sources**: values stored through `/secret`; values in well-known
   credential files (gh `hosts.yml`, `~/.pgpass`, service-account JSON keys under
   `~/.config/gcloud/`, `~/.codex/auth.json`, `~/.claude/.credentials.json`, hcloud `cli.toml`,
   `~/.docker/config.json` auths, `~/.netrc`, `~/.git-credentials`, `~/.npmrc`), re-read when their
   modification time changes; and **token-shaped strings** anywhere — published prefixes
   (`sk-ant-`, `sk-or-v1-`, `sk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `github_pat_`, `tskey-`,
   `xox[abprs]-`, `AKIA`/`ASIA`, `glpat-`, `hf_`, `AIza`), PEM private-key blocks, and assignments
   whose name says secret (`TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `APIKEY`,
   `PRIVATE_KEY`, `BEARER`, `CREDENTIAL`, any case, as a whole word or `_`-joined part) with a value
   of at least 16 characters and high character entropy. gitleaks' rule set is the reference for
   prefixes; bare hex or base64 without a prefix or a secret-named assignment is not redacted —
   commit hashes and checksums would drown the transcript. Encodings of known values (base64 with
   and without padding, hex, URL encoding) are redacted as today.
3. **Placeholders are reversible.** A known value reads `[secret:KEY]` (store keys) or
   `[secret:<file-label>]` (credential files); a pattern detection reads `[redacted:<kind>#<n>]`,
   numbered per session, the mod keeping the value in memory only. Before a Write, Edit,
   MultiEdit, NotebookEdit, or Bash call runs, every placeholder in its input is replaced by the
   value it stands for, so a model editing a file it saw redacted leaves the secret intact, and
   `Authorization: Bearer [secret:KEY]` in a command works like `$(cat …)`. The tool call as the
   transcript records it keeps the placeholder. An unknown placeholder (another session's number)
   is left as written.
4. **Linux.** Nothing in the mod assumes macOS; the store and the credential-file list resolve
   under `$HOME`.

What it cannot catch, stated so no one relies on it: a value the model deliberately slices,
reverses, or transforms. The person judged prompt-injection risk negligible for their setup; the
mod exists to stop accidents, which arrive as plain text or a common encoding.

## Out of scope

- Provisioning drivers (creating VMs, microVMs, containers on any provider) and choosing
  providers. The research behind the eventual choice — container runtimes, managed sandboxes,
  provider prices, Tailscale limits — is summarized in the Decision Log entry of 2026-10-15.
- Moving the session store's database, or the gateway, to the cloud.
- Running the Codex CLI on hosts (GPT models are reached through the gateway).
- sminos identities for sandboxes (a desk hub change).
- A credential proxy or broker (decided against: friction first; Decision Log).

## Execution

### Constraints that bind every milestone

- doperpowers is public: no host name, IP, account, project ID, secret name, or tailnet name of the
  person's in any doperpowers file, test, or commit message. Personal values live in the profile.
- `devcloud/` scripts are POSIX shell (bash) or Python 3.11+ standard library only (`tomllib` for
  TOML). No third-party dependency in the boot path.
- Never print a secret value — in commands, logs, `devcloud status`, or test output. Read values
  inside the command that uses them. Status and logs name keys only.
- Every boot step and job is idempotent; the second run of anything converges.
- Target Ubuntu 24.04 (x86_64 and arm64). The Macs remain the source of configuration; nothing a
  host runs commits or pushes to the config repository.
- Throwaway cloud resources created for testing are deleted the same day, and their deletion is
  recorded in Progress.
- Version bumps through `scripts/bump-version.sh`, in the commit that changes the plugin.

### Plan of Work

Work spans three repositories: doperpowers (this worktree, branch `devcloud`), the person's config
repository at `~/.claude` (commit to its current branch; its own sync job pushes), and `cua` at
`~/Developer/GitHub/cua` (branch and PR).

### M1 — Secrets guardrail mod in doperpowers; cua's copy retired

At its end, every session on a Mac with doperpowers gets Design §9's behavior, and the `cua`
plugin no longer registers `/secret`. Touches `hooks/mods/secrets.tsx` (new), `hooks/mods/register.tsx`,
`tests/mods/secrets.test.ts` (new), `CLAUDE.md`'s repo map (the `/secret` sentence), and in `cua`:
`hooks/mods/secrets.tsx` and its registration removed, its tests that covered the mod removed or
moved, its README and CLAUDE.md updated, version bumped. Interfaces: I1 (store), I2 (placeholders).
Decisions: port the store, pane, tiers, and prompt section from `cua`'s mod rather than rewriting
them — that code carries hard-won fixes (masking under mosh, the slug rule, case-insensitive
`projects`); remove its `guardReason` deny path. The detector is a pure function
(`detect(text) → spans`) so tests pin it without a session. Release both in one sitting — the
doperpowers version that adds the mod and the `cua` version that removes it are published
together — so two `/secret` registrations coexist only until both plugin caches update; both
mods scrubbing in that window is harmless. Does not touch:
`cua`'s `src/secrets/` store library or its device-credential flows. Proves acceptance 1–2; tests
also pin: no redaction of a 40-hex commit hash or a sha256 checksum; a known value split across a
tool result and the next row is still caught in each row it appears in whole; the transcript file
written by the engine carries placeholders, not values.

### M2 — devcloud core

At its end, `devcloud/` builds a credential-free image and boots a container from it into a
working host given a descriptor and seed (acceptance 3 against a container, with a stand-in
profile for tests). Touches `devcloud/` (new): `README.md` (the contract: descriptor, profile,
secrets map, services, status), `image/setup.sh`, `image/Dockerfile`, `boot/devcloud-boot`,
`boot/devcloud-services`, `boot/devcloud` (the `status` command and the jobs' entry points),
`boot/secrets.py` (the materializer), `tests/` (new, `devcloud/tests/run.sh`). Interfaces: produces
I3, I5, I6, I7; consumes I1 (writes `store` entries in its layout). Decisions: Secret Manager
access uses the REST API with a token from the seed (a JWT-signed exchange for a key file, the
metadata server on GCE), implemented with the standard library — the Google Cloud CLI is
installed for the user but the boot path does not depend on its login state; the config pull job
is `devcloud pull-config`, the secrets refresh `devcloud refresh-secrets`, both every 30 minutes;
`devcloud-services` restarts a crashed service with backoff and forwards SIGTERM to every child
(the session store shipper's final pass needs the signal); tests run the boot program in a
container against a fake Secret Manager (a local HTTP server) and a local bare repository standing
in for the config repository. Does not touch: the person's config repository (M3), sminos (M5).
Proves acceptance 3 (container, stand-in profile), 5 (container), 6.

### M3 — The person's profile and Linux compatibility

At its end, the person's real profile exists and their configuration runs cleanly on Linux.
Touches the config repository at `~/.claude`: `devcloud/profile.env` and `devcloud/secrets.toml`
(new; values in Secret Manager, not in the files); `statusline-command.sh` (BSD `date -r` replaced
by a form both `date`s accept); the notification hooks under `hooks/` (do nothing where
`osascript` is absent); `CLAUDE.md`'s gcloud line (true on the MacBook only, now stated per host);
removal of `sync/claude-config-sync.{service,timer}` and `sync/install-systemd.sh` (Design §5);
`README.md` (sync is pull-only on hosts). Populates Secret Manager with the secrets the profile
lists, reading each value from its source on a Mac inside the command that uploads it. Decisions:
the secret list is the one agreed in conversation — the GitHub token, the gcloud owner
service-account key, hcloud contexts, the session store's `~/.pgpass` line, the cua relay MCP
configs, and the API keys the person keeps in shell rc files — and excludes every OAuth grant a
refresh owner holds (Claude, Codex: the gateway's), browser-only tokens, and backup passwords.
Three keys exposed during design (a Claude OAuth token, an OpenRouter key, a market-data key) are
uploaded only after the person rotates them; until then their entries exist in `secrets.toml`
marked `optional = true`, and the materializer reports them `missing` without failing the boot. Does not touch: doperpowers.
Proves acceptance 3 with the real profile when run by M5; tests: the statusline renders on GNU
`date`.

### M4 — Project environments

At its end, `devenv up <name>` runs a repository's `devenv/` scripts on a Mac and on a host, and an
agent can write `devenv/` for a repository. Touches the config repository's `tools/devenv` (rewritten
around Interfaces §I4; registry entries under `envs/` keep naming repositories and refs),
`tools/tests/test_devenv_*.py`; doperpowers: `skills/devenv/SKILL.md` (new, authored and tested
with doperpowers:writing-skills), `devenv/` for doperpowers itself as the first instance; and
`devcloud/boot` step 10 plus the mirror cache (Design §7). Decisions: "changed since the last
successful run" is the repository's HEAD plus the hash of `devenv/` and of the lockfiles
`setup.sh` declares in a header comment; `start.sh` runs services in a tmux session named for the
project, as `devenv start` does today. Does not touch: projects other than doperpowers (each adopts
`devenv/` on its own schedule). Proves acceptance 8.

### M5 — sminos on hosts, and acceptance

At its end, the whole acceptance holds on one container and one throwaway VM. Touches
`devcloud/boot` step 9 (sminos daemon install for an enrolled persistent host, lingering, sandbox
identity hygiene) and `devcloud/README.md`. Runs acceptance 1–8 as written, on a container on a
machine with Docker and on a throwaway Ubuntu 24.04 VM in the person's cloud account (created with
the person's existing provider CLI, deleted the same day). The VM needs a one-time tagged
Tailscale auth key; generating one is the person's step (admin console), requested through the
dispatching session. Decisions: whether the container reaches tailnet peers through its host's
route is checked first, as the milestone's opening step (Docker's masquerade should carry it; if
it does not, the container gets the host's network namespace and the deviation is logged).
Proves acceptance 1–8.

### Concrete Steps

Run from the devcloud worktree unless stated.

    # M1
    tests/mods/run-mods-tests.sh
    # M2
    devcloud/tests/run.sh                      # expect: every case "ok"
    docker build -t devcloud-test -f devcloud/image/Dockerfile .
    # M2/M5 acceptance 3 (container): the descriptor and seed live outside the repo
    docker run --rm -v "$DESC":/etc/devcloud/boot.env:ro -v "$SEED":/run/devcloud/seed.json:ro devcloud-test
    docker exec <id> devcloud status           # expect: every step "ok"
    docker exec -u new <id> claude -p "reply ok"   # expect: ok
    # M3 (config repo)
    python3 -m unittest discover -s ~/.claude/tools/tests
    # M4
    devenv up doperpowers && devenv up doperpowers   # second run: "unchanged, setup skipped"

### Interfaces and Dependencies

**I1 — Secret store** (unchanged from `cua`): `~/.config/claude-secrets/<KEY>` and
`~/.config/claude-secrets/projects/<slug>/<KEY>`, one value per regular file, mode 0600, directory
0700, one trailing newline dropped on read; keys `[A-Za-z_][A-Za-z0-9_]*`.

**I2 — Placeholders**: `[secret:<KEY>]` for store and credential-file values (credential-file
labels are `<file-basename>:<field>`), `[redacted:<kind>#<n>]` for pattern detections (`kind`: the
rule's id, e.g. `github-pat`, `anthropic`, `pem`, `assignment`). Restored in the inputs of Write,
Edit, MultiEdit, NotebookEdit, and Bash.

**I3 — `secrets.toml`** (the materializer's input, in the profile):

    [[secret]]
    name = "<Secret Manager secret id>"   # required; latest version is read
    store = "KEY"        # optional: also written as ~/.config/claude-secrets/KEY (listed, scrubbed)
    env = "VAR"          # optional: exported through /etc/devcloud/env
    file = "~/path"      # optional: the value, or the template below, written here
    template = "..."     # optional: {value} substituted; without it the file is the value
    mode = "0600"        # default 0600; parent directories created 0700
    optional = true      # absent in Secret Manager → status "missing", boot continues

**I4 — `devenv/` contract**: `devenv/setup.sh` (required; run as the user from the repository root;
exit 0 on success; safe to re-run; a header line `# devenv: watches <glob> ...` names the lockfiles
whose change triggers a re-run), `devenv/start.sh` (optional; starts services, returns once they
are ready), `devenv/env` (optional; `KEY=value` lines and `secret:KEY=<Secret Manager id>` lines).

**I5 — Boot descriptor** `/etc/devcloud/boot.env`:

    DEVCLOUD_NAME=<host name>                  # unique; sandboxes sbx-<random>
    DEVCLOUD_KIND=vm|microvm|container
    DEVCLOUD_ROLE=persistent|sandbox
    DEVCLOUD_TAILSCALE=join|host|none
    DEVCLOUD_TS_AUTHKEY_FILE=<path>            # join only; deleted after use
    DEVCLOUD_SEED=file:<path>|gce-metadata
    DEVCLOUD_SM_PROJECT=<GCP project id>
    DEVCLOUD_CONFIG_REPO=<https clone URL>
    DEVCLOUD_CONFIG_BRANCH=<branch>            # default main
    DEVCLOUD_CONFIG_TOKEN_SECRET=<Secret Manager id of the GitHub token>
    DEVCLOUD_PROJECTS="<owner/repo[@ref]> ..." # optional
    DEVCLOUD_MIRROR_DIR=<path>                 # optional; sandboxes: the host's mirror cache

**I6 — Status**: `/var/lib/devcloud/status.json`, `{"steps": [{"name", "state": "ok|failed|skipped|missing", "at", "detail"}]}`; `detail` never holds a value. `devcloud status` prints one line per step.

**I7 — Services**: `pull-config` (30 min), `refresh-secrets` (30 min), `session-mirror ship`
(continuous), `sminos daemon` (persistent and enrolled only; its own systemd user unit). Under
systemd: units named `devcloud-<service>`; otherwise `devcloud-services` runs the same list.

## Surprises & Discoveries

(none yet)

## Decision Log

- Decision: Verification. One independent spec review by the `doperpowers:adversarial-reviewer`
  agent (technical-heavy spec) plus its buildability review of this five-milestone execution
  section, in the same round. Whole-branch review at the **high** rung of doperpowers:review-code
  (credentials and a guard on model context are at stake); M1's diff gets its own review at its
  boundary as part of the execution loop.
  Rationale: execspec's default for a multi-milestone spec; the rung follows the stakes.
  Date/Author: 2026-10-15, design session.
- Decision: Research summary behind the choices this spec defers (2026-10-15). For later
  provisioning: containers with a systemd-capable runtime on one persistent host are the cheapest
  sandbox substrate (sub-second start, no KVM); Firecracker needs a KVM host (bare metal or GCE
  nested virtualization); GCE spot VMs suit burst capacity (about 40 s to boot, cents per hour,
  keyless Secret Manager access through an attached service account); the free Tailscale plan's
  short-lived-node allowance rules out a tailnet node per sandbox. Credential proxying was weighed
  (it covers HTTP API tokens but not non-HTTP protocols, local signing, or tools with their own
  CA handling) and rejected for friction; the person judged prompt-injection risk negligible.
  Rationale: recorded so a driver initiative starts from it.
  Date/Author: 2026-10-15, design session.

## Outcomes & Retrospective

Pending — written at finish.
