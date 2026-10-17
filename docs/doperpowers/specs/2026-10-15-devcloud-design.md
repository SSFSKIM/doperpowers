# devcloud — a cloud host that works like your Mac, on any substrate

**Date.** 2026-10-15. **Status.** Design approved in conversation; independent review converged over three rounds;
awaiting the person's read before execution. **Prior art, reference only.**
`docs/doperpowers/specs/2026-10-02-personal-cloud-env-design.md` (the discarded devbox spec) and its
research under `docs/doperpowers/research/2026-09-30-personal-cloud-env/`;
`docs/doperpowers/specs/2026-10-02-project-env-manifest-design.md` (the manifest `devenv` reads
today, retired here); `infra/worker-host/` (body / soul / seeding).

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
reads and what the transcript keeps. The person's `/secret` mod (now in the `cua` plugin) refuses
any command that touches its store — too strict for daily use — yet knows only the values stored
through it, so tokens in other files (a proxy config, a shell rc) reached model context twice in
the session that produced this design. The guard moves into the new `devcloud` plugin and
changes from deny to redact; `/secret` itself — the command, its masked entry pane, the store —
stays in `cua`, which needs it to type secrets into GUIs and browsers; `cua`'s own guard drops its
refusals everywhere and yields to devcloud's wherever both are installed — a change the `cua`
project makes from a ticket this work files, against a marker this work defines.
The transcript half matters more than it did: the session store now copies every transcript to a
central database and an archive bucket, so a value that reaches a transcript is copied twice more.

How to see it working: on a fresh container started from the devcloud image with a boot
descriptor and the seed credential, `claude -p "reply ok"` answers through the gateway, `gh` and
`gcloud` are authenticated, the run's transcript appears in the session store, and the project's
`devenv/setup.sh` has run — with no step typed by hand.

## Progress

- [x] (2026-10-15) Design approved in conversation; spec written.
- [x] (2026-10-15) Review round 1 (design review and buildability review) folded.
- [x] (2026-10-16) Review round 2 folded; home files and the login shell added from the person's question.
- [x] (2026-10-16) Review round 3 (the round-2 diff) folded; review converged.
- [x] (2026-10-17) The person's read of the reviewed spec: approved as it stands.
- [x] (2026-10-17 13:40) M1 — The devcloud plugin and its secrets guard, reviewed clean after four fix
  waves (the Bash restoration rule narrowed each time; Decision Log). Release to both Macs and the
  `cua` ticket follow the M1 pull request's merge.
- [ ] `cua`'s ticket landed; acceptance 1–2 rerun with both plugins enabled, and once with `cua` alone.
- [ ] M2 — devcloud core: image, boot program, secrets materializer, pull-only config, services.
- [x] (2026-10-17 10:30) M3 — The person's profile, Linux compatibility, and a hardened apply step in their config repository
  (config repo, reviewed clean after two fix waves). Secret Manager: seven entries created by the person;
  one application key's entry waits on that key's rotation (`optional = true`, reports `missing`).
- [ ] M4 — Project environments: `devenv/` replaces the manifest, the runner keeps its commands, an authoring skill.
- [ ] M5 — sminos on persistent hosts, and acceptance on a container and a throwaway VM.

## Terms

- **devcloud plugin**: `devcloud/` in the doperpowers repository, published as a second plugin in
  the same marketplace: the secrets guard mod, the `devenv` skill, and the host image and boot
  program.
  doperpowers stays the workflow plugin; a person opts into devcloud by installing it.
- **Host**: a Linux userland devcloud has booted — VM, microVM, or container.
- **Substrate**: what the host runs on (VM, microVM, container). Only three things differ by
  substrate; everything else is shared (see Design §1).
- **Role**: `persistent` (long-lived, always-on, a sminos machine; requires systemd) or `sandbox`
  (minutes to hours, one task, discarded).
- **Boot descriptor**: `/etc/devcloud/boot.env`, the only per-host input a driver supplies
  (Interfaces I5).
- **Profile**: the person's private settings for devcloud, kept in their config repository at
  `~/.claude/devcloud/` (Design §3, Interfaces I8). The doperpowers repository is public; nothing
  personal lives in it.
- **Seed credential**: the one credential a host needs before it can fetch anything else — the
  person's Google Cloud service-account key file, mounted by the driver, or on GCE the metadata
  server of a VM with that account attached. It also becomes the user's `gcloud` identity and
  application default credentials (Design §6).
- **Gateway**: the person's model relay (a separate app) reachable on their tailnet; Claude Code
  reaches it through `ANTHROPIC_BASE_URL`. It holds every model credential; hosts hold none.
- **Session store**: the person's transcript mirror (`session-mirror`, a tool in their config
  repository's `tools/`), a Postgres reached over the tailnet; a host ships to it with
  `session-mirror ship`.
- **Mod**: a Claude Code function hook module (`hooks/mods/*.tsx`), loaded under
  `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`; see the repo map in `CLAUDE.md` and `hooks/mods/README.md`.
- **Handle**: the placeholder text the mod puts where a secret was (Design §9, Interfaces I2).

## Acceptance

Each check names who runs it and what they observe. `<img>` is the image M2 builds; the boot
descriptor and seed are prepared in M5's preflight. Every secret used by a check of the mod is a
made-up value written for the test, never a real one.

1. **Redaction, not refusal (Mac).** In a session with devcloud installed — with `cua` disabled
   until `cua`'s ticket lands, and with it enabled afterwards, when `/secret K` opens `cua`'s pane
   once and stores the value — `cat ~/.config/claude-secrets/K`
   for a stored key runs (no refusal) and the model sees `[secret:K]`. Printing a scratch file that
   holds a made-up `ghp_…` token shows a `[redacted:github-pat#<ns>.1]` handle, in a subagent as in
   the main loop. With the session's model traffic recorded through a local proxy, no recorded
   request holds a raw value, outside the paths §9 lists as not covered (the auto-mode
   classifier's request for a call a restored handle runs in); the session's transcript file holds none in any surface Design §9
   lists as covered (`grep -c <value> <transcript>` is 0), nor does the session store's copy of the
   session (its rows and its tool-result files, an oversized command output among them); every
   surface §9 lists as not covered was observed in M1's boundary probe.
2. **Handles restore exact bytes on write.** The model edits a file that holds a token it saw as a
   handle (an Edit whose `old_string` and `new_string` carry the handle); the file on disk still
   holds the real token afterwards, byte for byte. The same holds for a file holding a stored
   value's base64 spelling, and for a project-tier key that shadows a global one (the global value,
   printed, gets its own handle and restores to the global bytes). After the session is resumed in
   a new process and a different token is detected, a handle from before the resume is not restored
   to it: a write carrying the old handle writes the handle text and the tool result names it as
   not restored. When a stored key's value changes mid-session, the old value, printed again, reads
   `[superseded:K]` and is never restored. `ls`, `mv`, `test -f`, and writing a new file in `~/.config/claude-secrets/` all run.
3. **One boot, a working host (container).** `docker run --hostname <name>` of `<img>` with a boot
   descriptor (`DEVCLOUD_KIND=container`, `DEVCLOUD_ROLE=sandbox`, one project) and the seed
   mounted: within 5 minutes `devcloud status` reports every step `ok`; inside it,
   `claude -p "reply ok"` prints `ok` through the gateway; `gh auth status` and `gcloud auth list`
   show the expected identities and `gcloud secrets list` and an ADC consumer both succeed;
   `git config user.email` matches the Macs' and the user's login shell is zsh;
   `session-mirror ls` on a Mac lists the run's session under the container's host name; the
   project's `devenv/setup.sh` ran (its marker or output present).
4. **Same on a VM, with systemd.** On a throwaway Ubuntu 24.04 VM given the same image recipe and
   a descriptor with `DEVCLOUD_KIND=vm`, `DEVCLOUD_ROLE=persistent`: check 3's observations hold;
   `systemctl status` shows the devcloud services active; after `sudo reboot` they come back and
   `devcloud status` is all `ok` again.
5. **Receive-only configuration, reconciled.** On the VM, edit `~/.claude/settings.json`, then run
   the config pull job: the edit is gone and `git -C ~/.claude status --porcelain` lists no tracked
   change; `git -C ~/.claude push` fails. A profile change committed on a Mac (a managed-settings
   value) reaches `/etc/claude-code/managed-settings.json` at the next pull, without a reboot.
6. **Credential-free image.** No credential of the person's and no per-host input is baked into
   the image: (a) none of the person's known secret values — the store's and the Secret Manager
   entries', fed in-process to the guard's known-value matcher and compared without printing —
   appears anywhere in the image filesystem or `docker history` (the check that matters; M2's
   tests run it with made-up values, M5 with the real ones); (b) none of the credential files the
   guard knows exists in the image, and `/etc/devcloud/boot.env` is absent; (c) the pattern
   detector finds nothing outside package-manager-owned trees — dpkg files that verify unchanged,
   npm's `node_modules`, and the Claude Code and gcloud install trees, where vendored constants
   and fixtures match token shapes by the thousand.
7. **sminos on a persistent host.** On the VM, unenrolled, sminos runs local-only and `sminos chat`
   works in a project checkout; after the person enrolls it, the next boot (or `devcloud
   reconcile`) installs and starts the sminos daemon as a systemd user unit, and it survives a
   reboot. A sandbox never carries `$SMINOS_HOME/daemon/`, its hostname is unique, and its
   `DAEMON_BOOT_ID` differs from the host's. `DEVCLOUD_ROLE=persistent` without systemd as PID 1
   fails the identity step with that reason.
8. **A repository describes its own environment.** `devenv up <name>` on a Mac or a host clones
   the repository and runs its `devenv/setup.sh`; re-running it with nothing changed does not
   reinstall. `devenv claude`, `devenv shell`, and `devenv start|stop|status` work from `devenv/`
   as they did from the manifest. The authoring skill, pointed at a repository without `devenv/`,
   writes scripts that pass check 3 for that repository.

## Design

### 1. Substrate-agnostic by construction

Everything a host needs is one program, `devcloud-boot`, run as root at every boot. It reads one
input, the boot descriptor, and it is idempotent: running it again converges, never duplicates.
Three things differ by substrate, and each is a small adapter, not a fork of the logic:

| Varies | VM | microVM | container |
|---|---|---|---|
| How the image is produced | `image/setup.sh` on a builder, then a snapshot | `image/setup.sh` into a rootfs | `image/Dockerfile`, whose one build step is `image/setup.sh` |
| How the descriptor, seed, and name arrive | cloud-init writes them; boot sets the hostname | a metadata service or kernel argument writes them; boot sets the hostname | bind mounts (descriptor, seed); the driver passes `--hostname`, boot verifies it |
| What runs the services | systemd | systemd | `devcloud-services`, a small supervisor, as the entrypoint's foreground after boot |

`devcloud-services` is chosen at runtime: when PID 1 is systemd, the boot program installs units;
otherwise the container entrypoint (`devcloud-boot && exec devcloud-services`) supervises the same
service list itself. One list, two runners — the alternative, requiring systemd in every
container (Sysbox can provide it), was rejected because it forces a runtime choice on every
container driver. A **persistent** host requires systemd as PID 1 (a VM, a microVM, or a container
runtime that provides systemd): it runs the sminos daemon as a systemd user unit and must survive
reboots, neither of which the small supervisor provides. The boot program refuses the combination
at its first step.

A container cannot change its own hostname without `CAP_SYS_ADMIN`, which Docker does not grant
by default; so the container driver passes `--hostname <DEVCLOUD_NAME>` and the boot program only
verifies it, where on a VM or microVM it sets it.

Tailscale also varies: a VM or microVM joins the tailnet itself (`DEVCLOUD_TAILSCALE=join`, with a
one-time, short-lived, tagged auth key the driver supplies in a file that the boot program
deletes after use); a container uses its host's tailnet through the host's routing
(`DEVCLOUD_TAILSCALE=host`). A sandbox never joins the tailnet as its own node: the free
Tailscale plan bounds short-lived tagged nodes to 1,000 node-minutes a month (enforcement
announced), which per-sandbox joins would exhaust in days.

### 2. The image: tools, never credentials

`devcloud/image/setup.sh` (run as root on Ubuntu 24.04) installs everything that is the same on
every host: git, build tools, Python 3.12 with venv, uv, Node LTS, jq, tmux, mosh, gh, the Google
Cloud CLI, hcloud, Tailscale, Docker client, zsh, and Claude Code (native installer, as the user).
It creates the user, with zsh as the login shell as on the Macs, from three required build inputs — `DEVCLOUD_USER`, `DEVCLOUD_UID`,
`DEVCLOUD_HOME` — which the person sets to their Macs' account (on macOS a home is
`/Users/<user>`); the values live in the profile's `build.env` (Interfaces I8), never in
doperpowers. The home path is not cosmetic: transcripts record working directories, the session
store keys sessions by project directory names derived from them, and the person's tools
(`devenv`, `secret-env`, the statusline, the trust template) hard-code the Mac home; with the same
path a session started on a Mac resumes on a host and back. `/Users` is a plain directory on
Linux.

The image carries no credential, no boot descriptor, no `~/.claude` checkout, and no
`$SMINOS_HOME/daemon/`: a cloned enrollment would make two machines share one sminos identity
(their streams evict each other and their writers collide), and a cloned credential cannot be
revoked per host. Check 6 enforces this.

### 3. Public mechanism, private profile

The doperpowers repository is public, so the devcloud plugin holds only mechanism. Everything personal lives
in the person's private config repository (cloned to `~/.claude` on every host), under
`~/.claude/devcloud/` (Interfaces I8):

- `managed-settings.json` — the managed Claude Code settings every host gets (Design §6), the
  gateway's URL among them; the boot program's gateway check reads the URL from here, so the
  gateway is named in one place.
- `profile.env` — `KEY=value` lines for `/etc/devcloud/env`: time zone, locale, extra `PATH`
  entries, and any environment the person wants on every host.
- `secrets.toml` — what to fetch from Secret Manager and where to put it (Interfaces I3).
- `home/` — files copied into the user's home on every boot and reconcile, received like
  `~/.claude`: the git identity and global git settings (`.gitconfig`, `.gitignore`), `.tmux.conf`,
  and a host-safe `.zshrc` (the Macs' own rc files carry exported keys, so they are not copied;
  secrets reach hosts only through `secrets.toml`).
- `build.env` — the image's user inputs (Design §2), read on the machine that builds the image.

The boot descriptor carries just enough to reach the profile: the config repository's URL, the
Secret Manager project, and the name of the secret holding the GitHub token used to clone it.

### 4. Boot sequence

`devcloud-boot` runs these steps in order, each recorded in `/var/lib/devcloud/status.json`
(`devcloud status` prints it). A step's failure stops the boot with the step named; the next run
retries from the top. Nothing reaches the tailnet's services before step 6, because only the
profile (step 5) names them.

1. **Identity.** Refuse `DEVCLOUD_ROLE=persistent` without systemd as PID 1. Set the hostname to
   `DEVCLOUD_NAME` (VM, microVM) or verify it equals it (container). Write `SESSION_MIRROR_HOST`
   and, for a container (which sees its host's boot id), a fresh `DAEMON_BOOT_ID` into
   `/etc/devcloud/env`. Sandbox names must be unique; drivers use `sbx-<random>`.
2. **Tailnet attach.** When `DEVCLOUD_TAILSCALE=join`, join with the auth key from the file, then
   delete the file. Otherwise nothing to do here.
3. **Seed.** `DEVCLOUD_SEED=file:<path>`: activate the key in a root-private gcloud configuration
   directory (`CLOUDSDK_CONFIG=/var/lib/devcloud/gcloud`), from which every later step takes an
   access token (`gcloud auth print-access-token`); `gce-metadata`: tokens come from the metadata
   server. The token then calls the Secret Manager REST API from the standard library.
4. **Bootstrap secret.** Fetch the GitHub token named by `DEVCLOUD_CONFIG_TOKEN_SECRET`.
5. **Configuration.** As the user, clone (or fetch and reset) the config repository into
   `~/.claude` (Design §5), passing the token through a credential helper that reads it from a
   root-owned temporary file — never in a URL or in `.git/config`; then read the profile.
6. **Tailnet check.** The gateway named in the profile's `managed-settings.json` answers.
7. **Secrets.** Materialize every entry of `secrets.toml` (Interfaces I3).
8. **Home and credentials.** As the user: copy the profile's `home/` files into the home; then,
   with a file seed, `gcloud auth activate-service-account` with the seed key, the same key written
   as application default credentials, and the Secret Manager project set as the default (on GCE
   the metadata server serves both); then `gh auth setup-git`, which adds its credential helper to
   the copied `.gitconfig`.
9. **Apply.** Run the config repository's `sync/apply.py` (plugins, marketplaces, MCP servers,
   `~/.claude.json` seeding, the `devenv` link) as the user.
10. **Managed settings and environment.** Write `/etc/claude-code/managed-settings.json` from the
    profile and `/etc/devcloud/env` from boot step 1, the profile, and `secrets.toml`'s `env`
    targets (Design §6).
11. **Services.** Install or start: the config pull job, the secrets refresh job, and the session
    store shipper (`session-mirror ship`); on an enrolled persistent host, the sminos daemon
    (Design §8). A service whose unit or environment changed is restarted.
12. **Projects.** For each `DEVCLOUD_PROJECTS` entry, `devenv up` (Design §7).

### 5. Configuration is received, never sent

A host keeps `~/.claude` as a clone it only receives: the pull job runs `git fetch` then
`git reset --hard origin/<branch>` every 30 minutes, and the clone's push URL is set to an invalid
value so a push fails loudly. A change made on a host — a model pick saved into `settings.json`, a
permission rule — lasts until the next pull, by design: configuration is authored on the Macs.
Machine-local differences live only where git does not reach: managed settings (Design §6) and
untracked files.

What the pull brings is applied, not just checked out: when the fetched commit differs from the
last one applied, the job runs `devcloud reconcile` — boot steps 5 through 11 (profile, tailnet
check, secrets, home and credentials, apply, managed settings and environment, services) — recording each
step in the status file as a boot does. Without it a gateway change made on a Mac would reach the
clone but not the root-owned managed settings, whose precedence no synced setting overrides.
Projects (step 12) are not reconciled; `devenv up` is run when the work needs it.

The config repository's existing Linux sync unit (`sync/claude-config-sync.{service,timer}`,
`sync/install-systemd.sh`) commits and pushes; it is removed in M3, because a pushing Linux host
contradicts this rule.

### 6. Environment: three places, by who reads it

Processes on a host are not all started by a login shell — `claude --bg` sessions are started by
Claude Code's own daemon, services by systemd or `devcloud-services` — so a variable set only in a
shell rc reaches some of them and not others. Each setting goes where every reader sees it:

- **Claude Code settings** go in `/etc/claude-code/managed-settings.json`, which every session
  reads however it started, copied from the profile. It holds only the keys a host must change;
  everything else comes from the synced `settings.json`, because settings scopes merge `env` key by
  key (verified 2026-10-16 with a higher-precedence `--settings` scope; M2 verifies the managed
  scope on a host). The keys: `ANTHROPIC_BASE_URL`, which the synced file sets to the Mac's own
  loopback relay, pointed at the gateway across the tailnet, and its non-secret marker token; the
  gateway's feature switches (`ENABLE_TOOL_SEARCH`,
  `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING`, `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`),
  pinned because the gateway's desktop app writes them into the synced `settings.json` when it
  turns routing on and removes them when it turns routing off, so a commit taken while routing was
  off carries none; and empty values for Mac-only settings the synced file carries (a
  browser-extension token, `CLAUDE_CODE_PLUGIN_DIRS` pointing at an untracked directory).
- **Credentials** go in files every process reads whatever its environment: gh's `hosts.yml`,
  hcloud's `cli.toml`, `~/.pgpass`, MCP configs (from `secrets.toml`), and gcloud's credential store
  and application default credentials (from the seed, boot step 8 — writing a key file is not
  enough; `gcloud` reads its own store).
- **Everything else** goes in one environment file, `/etc/devcloud/env`, loaded by every shell —
  `/etc/zsh/zshenv` for zsh (every zsh reads it: login, interactive, and the `zsh -c` Claude Code's
  Bash tool runs; zsh does not read `/etc/profile.d/`), `/etc/profile.d/devcloud.sh` for bash — and
  named as `EnvironmentFile` (or loaded by `devcloud-services`) for services: the profile's `profile.env`, the identity variables from boot
  step 1, and the `env` targets of `secrets.toml`.

Project-specific environment belongs to the project's `devenv/` (Design §7).

### 7. Projects describe their own environment: `devenv/`

A repository that wants to run on a host carries a `devenv/` directory at its root (contract in
Interfaces I4): `setup.sh` installs its dependencies and is safe to re-run; `start.sh`, optional,
runs its services; `validate.sh`, optional, checks the environment; `env`, optional, names its
environment and the Secret Manager secrets it needs. Scripts replace the JSON manifest
(`.devbox/environment.json`) the person's `devenv` tool reads today, which no repository's default
branch adopted (it lives only on unmerged `devbox-manifest` / `project-env-manifest` branches);
scripts won because a repository's owner can express any install in a script, while the manifest
needed a schema for every case. The devcloud plugin's `devenv` skill teaches an agent to write
`devenv/` for a repository (M4).

The runner (`tools/devenv` in the config repository) changes where it reads a project's
declaration, not what it does for the person. Kept: every command (`up`, `claude`, `shell`,
`start|stop|status`, `validate`, `show`, `list`); the registry (`~/.claude/envs/<name>.json`, naming
a project's repositories, refs, and root); the generated runtime state under `.devbox/`
(gitignored: `env.sh`, `secrets.sh`, logs, the install stamp) and what consumes it (the shell-rc
hook `tools/devenv-rc.sh`, the non-secret environment merged into `.claude/settings.local.json`,
secrets resolved strictly at launch and non-strictly for the install); the install's change
detection, whose header line (`# devenv-inputs: <glob> ...`) `setup.sh` keeps; `reap` supervision
of the install. Mapped: the manifest's `install` → `devenv/setup.sh`; `env` and `secrets` →
`devenv/env`; `validate` → `devenv/validate.sh`; `services` → `devenv/start.sh`, which `devenv
start` runs in tmux session `<name>` (`stop` ends that session's process groups, `status` reports
whether it runs). Retired, because scripts or the person's stated risk judgment subsume them: the
per-service windows and readiness probes, the linked start skill, and the `sandbox`/`network`
settings (`devenv claude --sandbox`).

Hosts name projects in the descriptor (`DEVCLOUD_PROJECTS`, Interfaces I5): an entry `<name>`
runs `devenv up <name>` against the registry; an entry `<owner>/<repo>` runs `devenv up <repo>
--url https://github.com/<owner>/<repo>.git`, creating the registry entry on that host when absent;
an `@<ref>` suffix on either overrides the registry's ref for the root repository on that host.

The `devenv` skill (in the devcloud plugin, invoked as `/devcloud:devenv` in a repository or
triggered by asking for one) writes a repository's `devenv/` from what the repository already
says about itself: its CI first — `.github/ci-kit.yml` where the repository has adopted ci-kit
(its `setup` and gate commands), else its workflows — because that install path is one something
already runs and tests; then its manifests and lockfiles, compose files, bootstrap scripts and Makefile targets, and the
setup section of its README. It writes `setup.sh` with the `# devenv-inputs:` lines naming the
lockfiles it read, working on macOS and Ubuntu alike (the package manager chosen by platform);
`start.sh` only when the repository runs long-lived services; `validate.sh` as the repository's
quickest real check; and `env` with non-secret values and `secret:` lines naming Secret Manager
ids, asking the person for an id it cannot infer and never reading a value. It then proves what it
wrote — `devenv up` twice (the second run skips setup), then `devenv validate`, and on Linux in a
devcloud sandbox container when one is available — and commits the result on a branch in that
repository. A repository whose `devenv/` already exists gets a review against the same sources
rather than a rewrite.

Sandboxes start from a bare mirror their persistent host keeps per repository
(`/srv/devcloud/mirrors/<owner>/<repo>.git`, refreshed by the host), cloning with `--reference`
so a checkout takes seconds.

### 8. sminos on hosts

sminos 7.159.0 made Linux a first-class sminos machine: `sminos daemon install` writes a systemd
user unit. A **persistent** host is a sminos machine: enrolled once by the person
(`sminos hub enroll`, which takes a code made in their browser — deliberately a human step, since
the code carries the organization's key), after which boot step 11 runs `sminos daemon install`,
enables lingering for the user, reloads the user manager, and enables and starts the unit
(`install` only writes it). Unenrolled, the host's projects run local-only. A **sandbox** is not a
sminos machine: enrolling one would need the organization key inside it and would leave its
members on the desk as idle ghosts after it vanishes. Its sessions are recorded by the session
store instead, and whoever launched the sandbox (a seat on its host, or the person) owns its
outcome. Giving sandboxes their own short-lived identities is a hub change, deferred (Out of
scope).

### 9. The secrets guard mod

The work divides between two plugins by what each is for. `cua` (repository
`~/Developer/GitHub/cua`) keeps `/secret`: the `/secret [-g] KEY` command and its masked entry
pane, the store and its library (`~/.config/claude-secrets/KEY` global,
`~/.config/claude-secrets/projects/<slug>/KEY` per project, mode 0600 files in a 0700 directory,
the slug rule and the reserved `CUA_DEVICE_*` keys in the global tier, as `cua`'s
`src/secrets/store.mjs` documents), the system-prompt section listing the stored keys and how to
use one (`"$(cat ~/.config/claude-secrets/KEY)"`), and its GUI and browser typing of
`{{secret:KEY}}`. Installed alone, `cua` keeps a guard of its own, reduced to scrubbing: it
replaces stored values and their encodings with `[secret:KEY]` as it does today, and no longer
refuses any command for touching the store.

devcloud's `devcloud/hooks/mods/secrets.tsx` is the guard: it reads the same store (Interfaces
I1), registers no `/secret` command, and adds one system-prompt line saying what its handles mean
and that they restore on write. When a session starts it sets the guard marker (Interfaces I9,
in the session's `$.state`; checked by `cua`'s mod at hook time, so load order does not matter),
and `cua`'s scrubbing stands down, so one guard decides every handle: two scrubbers in
sequence would lose the encoding a handle names.

The guard differs from `cua`'s in four ways:

1. **Redact, never refuse.** No tool call is denied for touching the store. Values are replaced
   wherever the mod's hooks reach before the text leaves the process: the tool's result as the
   model reads it, the tool's own record (`toolUseResult`), and every row appended through
   `session.append`. Refusal bought nothing redaction does not: a command that prints a value is
   caught at its output, and refusing reads also refused writes, moves, and existence checks.
   These hooks are not every path text takes. An attachment row keeps its original payload beside
   the rendered text a rewrite cleans; manual compaction rows bypass `session.append`
   (`hooks/mods/README.md`); the system prompt is composed, not appended; images are not text; and
   an oversized tool output is written by the engine to the session's `tool-results/` directory
   before the hook sees the result, its path returned as `persistedOutputPath`. That last file is
   one the session store ships, so the mod rewrites it in place, scrubbed, before the tool call
   returns, and the session store ships a `tool-results/` file only once it has been unchanged for
   a settle interval, so the rewrite lands before the first copy leaves the machine.
   M1 opens with a boundary probe — synthetic values sent through each path (oversized and
   background command output among them), the model traffic recorded through a local proxy, the
   transcript and the session store's copy searched — and for each path either intercepts it with
   a hook that reaches it or lists it in this section as not covered. The guarantee the mod states
   is exactly the covered list.

   **Probe result (2026-10-17, Claude Code 2.1.302, headless sessions through the gateway).**
   Covered — no made-up value in any recorded request, the transcript files, or the session
   store's copy: a tool's result and its record, in the main loop and in a subagent; an
   oversized command output, its preview and its `tool-results/` file (rewritten 39 ms after the
   engine created it); a background command's output as the model reads it and its
   notification; a subagent's result; the person's prompt; `CLAUDE.md` as a context block
   (`prompt.context`); the composed system-prompt sections (`prompt.compose`); an attachment's
   text as a request carries it (`prompt.attachment`); a manual compaction's instructions and
   its summary (`session.compact`, which reaches both: the compaction bypass named above does
   not leave them raw). Not covered:
   - an attachment row's own payload in the transcript file: a changed file the model had read,
     and the files the engine attaches again after a compaction (a background command's output
     file among them), keep their content beside the scrubbed rendering, so the session store's
     copy holds it too (observed);
   - system-prompt text given with `--system-prompt` or `--append-system-prompt`, which the
     engine adds after composition: every request carries it, and the transcript keeps it in its
     `prompt_snapshot` attachment rows and `api-request-shape` rows (observed);
   - a background command's output file in the engine's temporary directory: local, never
     shipped, read by the model only through a scrubbed tool result (observed);
   - the call a restored handle runs in: the permission dialog shows it, a command's arguments
     are visible to the machine's processes while it runs, and in auto mode a call the mode
     sends to its classifier is judged with its values in place — the classifier's request (a
     model call through the same gateway) carried a restored global value in the acceptance run
     (observed for a Write); `tool.check`'s input is pinned, so no hook can hand it the handles;
   - where an organization manages Claude Code: a plugin a person installs gets no
     `prompt.compose`, `prompt.context`, `prompt.attachment` or `session.compact` hook there
     (`claude plugin validate`), so those four paths are then not covered.
2. **Known values from three sources**: values stored through `/secret` (every project's tier, not
   only the session's: a command can print any of them); values in well-known
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
3. **Handles name what they stand for.** Each distinct redacted byte string gets its own handle
   (Interfaces I2): a stored value's encoded spelling gets the key's handle with the encoding
   named, a global value shadowed by a project key gets a handle naming its tier, a credential-file
   value names its file and field, and a pattern detection carries a namespace the mod draws at
   random when it starts, never reused. A known-value handle names a credential, not bytes frozen
   in time: like `$(cat …)`, it restores to the credential's current value in the named spelling,
   in this process or a resumed one — after a rotation, a command or a written file gets the
   current credential, which is what it wants, and an Edit whose `old_string` carries the handle
   against a file still holding the old value fails at the engine's own match, visibly. A value a
   key or credential-file field held earlier in this process stays redacted, as
   `[superseded:<label>]`, which restores nothing. A pattern handle stands for exactly the bytes it
   replaced.
   Before a Write, Edit, MultiEdit, NotebookEdit, or Bash call runs, every known-value handle and
   every pattern handle this process issued is replaced by its bytes, so a model editing a file it saw redacted leaves
   the secret intact, and `Authorization: Bearer [secret:KEY]` in a command works like `$(cat …)`.
   In a Bash command (its `command` alone) a handle is restored only where that is shown safe,
   and nothing is ever quoted:
   - the value is inert: non-empty, of `[A-Za-z0-9_./+:@-]` with `=` and `%` past the first
     character, and no `=` right after `=` or `:` except in a trailing run (base64 padding),
     since zsh's `MAGIC_EQUAL_SUBST` reads `==cmd` and `:=cmd` as `=cmd`;
   - the command holds no `<<` (heredoc or here-string), backtick, `((`, `$((`, `$[`, `${`,
     `[[`, `let`, `integer`, `float`, `declare`/`typeset`/`local`/`export`/`readonly` with a
     flag, comment or line continuation;
   - the handle stands in a plain string or a plain word, judged over the whole of it rather
     than its neighbours: inside `'…'`; inside a `"…"` whose other content has no `$`, backtick,
     `\` or `!`; or in an unquoted word (a maximal run between whitespace and `; | & ( ) < >`)
     whose other characters are all of the inert alphabet — so no quote, `$ { } [ ] * ? \ ~` —
     and which, restored, is inert as a whole (no leading `=` or `%`, no `==` or `:=` but a
     trailing run), is not the target of a redirection, and touches no `(` but one that opens a
     subshell or a substitution.
   So `"Authorization: Bearer [secret:K]"`, `'…[secret:K]…'`, `--token=[secret:K]`,
   `X=[secret:K] cmd` and `https://user:[secret:K]@host` restore; `$USER:[secret:K]` (a zsh
   modifier), `=[secret:K]`, `${X/[secret:K]/…}`, `> [secret:K]` and `{a,[secret:K]}` do not.
   A value that is not inert is never restored into a command. Every handle left in a command
   gets one line in the tool's result naming a read that works there and prints exactly the
   value's bytes (`devcloud/hooks/mods/secrets-reads.tsx`): for a store key
   `"$(cat <its tier's store file>)"`; for a JSON field `jq -j`; for `gh`'s hosts file
   `gh auth token`; for a TOML, `.pgpass`, `.netrc`, `.git-credentials` or `.npmrc` value a
   `python3` read that undoes the file's own quoting or escaping (and picks the `#n`th of
   repeated entries); for an encoded spelling that read piped into its encoding, with no `$()`
   in between; for a value that ends in a newline, which `"$(…)"` would drop, the read to pipe
   or pass as `<(…)`; for a pattern handle, which has no source on disk, a file tool writing it
   to a temporary file (file tools restore it) and `"$(cat <that file>)"`. The command still
   runs. Executing the restored commands under bash (also `--posix` and `-f`) and zsh (also with
   `magic_equal_subst`, `extendedglob`, `noglob`, `braceccl` and `kshglob`) over a matrix of
   values and command shapes, and each read against real files, proves it
   (`devcloud/tests/mods/shell-exec.ts`). File tools get the bytes raw: their content
   is not parsed by a shell. A handle-like text that does not parse (a space inside it) is named
   as not restored too.
   The tool call as the transcript records it keeps the handle. A handle that cannot be restored —
   a pattern handle another process issued (another session's, or this session's from before a
   resume), a `[superseded:…]` handle, a key no longer stored — is left as written and the tool's
   result carries one line naming it as not restored, so the model sees a literal write
   rather than learning of it later.
4. **Linux.** Nothing in the mod assumes macOS; the store and the credential-file list resolve
   under `$HOME`.

What it cannot catch, stated so no one relies on it: a value the model deliberately slices,
reverses, or transforms; a secret inside an image; an oversized output whose process is killed in
the moment between the engine persisting it and the mod rewriting it (the file then stays raw and
ships after the settle interval); and the paths the boundary probe lists as not covered. The person judged prompt-injection risk negligible for their setup; the mod exists to
stop accidents, which arrive as plain text or a common encoding.

## Out of scope

- Provisioning drivers (creating VMs, microVMs, containers on any provider) and choosing
  providers. The research behind the eventual choice — container runtimes, managed sandboxes,
  provider prices, Tailscale limits — is summarized in the Decision Log entry of 2026-10-15.
- Moving the session store's database, or the gateway, to the cloud.
- Running the Codex CLI on hosts (GPT models are reached through the gateway).
- Model credentials on hosts, and their rotation: the gateway owns both.
- sminos identities for sandboxes (a desk hub change).
- Persistent hosts without systemd.
- A keyless seed (workload identity federation against an issuer the person runs) — the right
  move when hosts multiply or one is less trusted than the Macs (Decision Log).
- A credential proxy or broker (decided against: friction first; Decision Log).

## Execution

### Constraints that bind every milestone

- The doperpowers repository is public: no host name, IP, account or user name, project ID,
  secret name, or tailnet name of the person's in any file, test, or commit message written there
  by this work. Personal values live in the profile; examples use neutral placeholders.
- `devcloud/` scripts are POSIX shell (bash) or Python 3.11+ standard library only (`tomllib` for
  TOML), plus the command-line tools the image installs (`gcloud` signs the seed's token exchange;
  the standard library has no RSA signing). No third-party Python package in the boot path.
- Never print a secret value — in commands, logs, `devcloud status`, test output, or a command
  line another process can read. Read values inside the command that uses them. Status and logs
  name keys only.
- Every boot step and job is idempotent; the second run of anything converges.
- Target Ubuntu 24.04 (x86_64 and arm64). The Macs remain the source of configuration; nothing a
  host runs commits or pushes to the config repository.
- Throwaway cloud resources created for testing are deleted the same day, and their deletion is
  recorded in Progress.
- Version bumps in the commit that changes the plugin: doperpowers through
  `scripts/bump-version.sh` as today; the devcloud plugin carries its own version (starting 0.1.0,
  in `devcloud/.claude-plugin/plugin.json` and its marketplace entry), bumped by the same script
  once M1 teaches it to take the plugin to bump. A doperpowers bump never moves devcloud's
  version, nor the reverse.
- doperpowers' CI is ci-kit (`.github/ci-kit.yml`, schema in ci-kit's `docs/adopting.md`). Every
  test suite this work adds becomes a gate there, scoped by `paths` to the files it covers, and
  the existing `repo-checks` gate stays green with a second plugin in the marketplace. The ci-kit
  session (sminos `@doperpowers/CI-opt`) is told when doperpowers' gates change; ci-kit owns the
  schema, doperpowers owns its own file.

### Plan of Work

Work spans two repositories: doperpowers (this worktree, branch `devcloud`; the devcloud plugin
lives in its `devcloud/` directory) and the person's config repository at `~/.claude` (commit to
its current branch; its own sync job pushes). `cua` (`~/Developer/GitHub/cua`) receives a ticket
after M1 and is changed by its own project, not here. Human steps — reviewing the secret inventory, rotating
exposed keys, generating a Tailscale auth key, enrolling a host — are requested through the
dispatching session at the points the milestones name, and the milestone waits for them there.

### M1 — The devcloud plugin and its secrets guard

At its end, the devcloud plugin exists, every session on a Mac with it gets Design §9's behavior
(proven with `cua` disabled), devcloud sets the guard marker (Interfaces I9), and a ticket asks
the `cua` project for its half. Touches, in doperpowers: the plugin skeleton — `devcloud/.claude-plugin/plugin.json`, its entry in `.claude-plugin/marketplace.json`,
`devcloud/hooks/hooks.json` naming `./mods/register.tsx` under `modules`, `devcloud/README.md`
(what the plugin is; M2 adds the host contract) — and `devcloud/hooks/mods/{register.tsx,
secrets.tsx,tsconfig.json}`, `devcloud/tests/mods/secrets.test.ts` with its runner
(`devcloud/tests/mods/run.sh`, staging like `tests/mods/run-mods-tests.sh` if `claude plugin test`
cannot take the folder directly), `scripts/bump-version.sh` and `.version-bump.json` (a plugin to
bump), `CLAUDE.md`'s repo map (a `devcloud/` row; the `/secret` sentence: the command stays in
`cua`, the guard is devcloud's), and `.github/ci-kit.yml` (a `devcloud-mods` gate running
`devcloud/tests/mods/run.sh`, installed like the `mods` gate, `paths: ["devcloud/**",
".github/**"]`; `repo-checks`' version-bump and marketplace-manifest tests extended for the second
plugin). In
the config repository: `sync/plugins.manifest.json` gains `devcloud@doperpowers`, and
`tools/session-mirror` ships a `tool-results/` file only once it has been unchanged for a settle
interval (Design §9.1), with a test. `cua` is not touched by this initiative: its half — dropping
its `guardReason` refusals, and its scrubbing standing down when the I9 marker is set, with
`/secret`, the pane, and the prompt section untouched; its tests that pinned refusals re-pinned to
the same commands running with values scrubbed, plus a test of each marker state; its README,
plugin description, and CLAUDE.md; a version bump — is a ticket for the `cua` project, registered
through doperpowers:issue-tracker as soon as M1's marker is merged, so `cua` can land it while
M2–M5 run. Interfaces: produces I9; consumes I1 (store), I2 (handles).

Order of work. First the boundary probe (Design §9.1): a recording proxy on localhost forwarding
to the person's gateway, a session with the new mod pointed at it, and synthetic values pushed
through a tool result, an oversized command output (persisted to `tool-results/`), a background
command's output, a subagent's result, a file attachment (a file the model read, changed on disk),
a manual compaction, and the system-prompt section; record which reach the recorded requests, the
transcript, or the session store's copy (`session-mirror pull` of the probe session), add interception where a hook reaches the path, and write the rest
into §9's not-covered list with the date. Then the guard: port the store reading (tiers, the slug
rule, case-insensitive `projects`) and the scrubbing of known values and their encodings from
`cua`'s mod rather than rewriting them — that code carries hard-won fixes — leaving its
`guardReason` deny path, `/secret`, and the pane behind. The detector is a pure function
(`detect(text) → spans`) so tests pin it without a session.

Release: install devcloud on both Macs (the plugins manifest entry, then `sync/apply.py` or
`claude plugin install`). Until the `cua` ticket lands, a session with both plugins runs both
guards: `cua`'s refusals remain (strict, as today) and `cua`'s scrubbing may reach a stored
value's encoded spelling before devcloud's, which then reads `[secret:KEY]` rather than
`[secret:KEY~b64]` — the one restoration the interim can get wrong, limited to encoded stored
values. So M1 proves acceptance 1–2 in fresh sessions with `cua` disabled; the run with both
plugins enabled is repeated when the ticket lands (an open item in Progress until then), together
with one session with devcloud disabled, where `cua` alone scrubs a stored value without refusing.

Does not touch: `cua`. Proves acceptance 1–2 (with `cua` disabled until its ticket lands); tests also pin: no redaction of a 40-hex commit hash or a sha256 checksum; a
known value split across a tool result and the next row is still caught in each row it appears
in whole; the transcript file written by the engine carries handles, not values; a resumed
process does not restore a pre-resume pattern handle to a newly detected token; a stored value
changed mid-session reads `[superseded:KEY]` afterwards and `[secret:KEY]` restores the new value;
an oversized output's persisted file holds handles before the call returns.

### M2 — devcloud core

At its end, `devcloud/` builds a credential-free image and boots a container from it into a
working host given a descriptor and seed, against a stand-in profile and with no projects (step
12 `skipped`); the project half of acceptance 3 waits for M4 and is proven in M5. Touches
`devcloud/` (the plugin M1 created): `README.md` (adds the host contract: descriptor, profile,
secrets map, services, status),
`image/setup.sh`, `image/Dockerfile`, `boot/devcloud-boot`, `boot/devcloud-services`,
`boot/devcloud` (`status`, `reconcile`, and the jobs' entry points), `boot/secrets.py` (the
materializer), `tests/` (new, `devcloud/tests/run.sh`), and a `devcloud` gate in
`.github/ci-kit.yml` running it on the hosted Ubuntu runner, which has Docker (`paths:
["devcloud/**", ".github/**"]`). Interfaces: produces I3, I5, I6, I7, and the reader side of I8;
consumes I1 (writes `store` entries in its layout).

Decisions: Secret Manager access is the REST API called from the standard library with an access
token from `gcloud` running against the root-private configuration the seed was activated into (a
key-file seed) or from the metadata server (GCE); the user's own gcloud state is never the boot
path's. The config pull job is `devcloud pull-config` (fetch, reset, and `devcloud reconcile` when
the commit moved); the secrets refresh is `devcloud refresh-secrets`; both every 30 minutes.
`devcloud-services` restarts a crashed service with backoff and forwards SIGTERM to every child (the
session store shipper's final pass needs the signal). Steps run strictly in order — `apply.py`
creates the `devenv` link step 12 calls. Tests run the boot program in a container against a fake
Secret Manager (a local HTTP server), a local bare repository standing in for the config
repository (holding a stand-in profile and a stand-in `sync/apply.py`), and a fake metadata
server as the token source (`DEVCLOUD_SEED=gce-metadata` with the metadata host pointed at it);
the key-file exchange through `gcloud` is proven against Google with the person's seed in M5's
preflight. The first boot in the tests starts from no cached profile and no inherited gateway
environment.

Does not touch: the person's config repository (M3), sminos (M5). Proves acceptance 3 (container,
stand-in profile, no projects), 5 (container, including a reconciled profile change), 6.

### M3 — The person's profile, Linux compatibility, and a hardened apply step

At its end, the person's real profile exists, the secrets it lists are in Secret Manager, and their
configuration applies cleanly on Linux. Touches the config repository at `~/.claude`:
`devcloud/managed-settings.json`, `devcloud/profile.env`, `devcloud/secrets.toml`,
`devcloud/build.env` (new; secret values in Secret Manager, never in the files);
`sync/apply.py`; `statusline-command.sh` (BSD `date -r` replaced by a form both `date`s accept);
the notification hooks under `hooks/` (do nothing where `osascript` is absent); `CLAUDE.md`'s
gcloud line (true on the MacBook only, now stated per host); removal of
`sync/claude-config-sync.{service,timer}` and `sync/install-systemd.sh` (Design §5); `README.md`
(sync is pull-only on hosts).

`sync/apply.py` becomes fit to run inside a boot that stops on failure and never logs a value: a
failed required operation (marketplace add, plugin install, MCP add) makes it exit non-zero after
the remaining operations are attempted, and its printed commands name the operation and the
server or plugin, never the MCP configuration JSON or a failing command's raw output beyond a
first line with known secrets removed. No secret value travels in a command line: the shared
MCP configuration (`sync/mcp.json`) carries none — it carries none today — and a server that needs
one on hosts names it as a `${VAR}` reference the engine expands from the environment
(`/etc/devcloud/env`, from `secrets.toml`); M3 verifies the engine expands references at user
scope before relying on it, and a server it cannot carry that way is left off hosts and named in
the inventory. Tests: a failing fake `claude` makes it exit non-zero; a synthetic Authorization
header placed in an MCP config appears in no output and in no argument the fake `claude`
receives.

The secret inventory. Draft `secrets.toml` from what hosts need — the GitHub token (bootstrap,
gh's `hosts.yml`), hcloud contexts, the session store's `~/.pgpass` line, the cua relay MCP
configs, and the application API keys the person keeps in shell rc files — and exclude every
model credential (any Claude or OpenAI credential, OpenRouter's key: the gateway's), every OAuth
grant a refresh owner holds, browser-only tokens, backup passwords, and the gcloud key (it is the
seed, not an entry). Before any upload, send the inventory — secret names, sources, and targets,
no values — to the dispatching session for the person's review, together with the list of keys
exposed during design that must be rotated first; upload each approved entry reading its value
from its source on a Mac inside the uploading command, and upload a rotated key only after the
person confirms its rotation (until then its entry is `optional = true` and reports `missing`).

Does not touch: doperpowers. Proves, with M5: acceptance 3 with the real profile. Tests: the
statusline renders on GNU `date`; `apply.py` as above.

### M4 — Project environments

At its end, `devenv` runs a repository's `devenv/` on a Mac and on a host with every command the
person uses today, and an agent can write `devenv/` for a repository. Touches the config
repository's `tools/devenv` (rewritten around Interfaces I4 and Design §7's kept / mapped / retired
list), `tools/devenv-rc.sh` (unchanged in contract; touched only if the generated paths move),
`tools/tests/test_devenv_*.py` (tests of kept behaviors adapted to `devenv/`, tests of retired
features removed, new tests for the descriptor bridge), the registry entries under `envs/` (refs
that pin the retired manifest branches return to each repository's default branch); doperpowers:
`devcloud/skills/devenv/SKILL.md` (new, authored and tested with doperpowers:writing-skills),
`devenv/` at the doperpowers repository's root as the first instance, and `devcloud/boot` step 12
plus the mirror cache
(Design §7). Decisions: "changed since the last successful run" is the repository's HEAD plus the
hash of `devenv/` and of the files `setup.sh`'s `# devenv-inputs:` lines name; `devenv up --ref
<ref>` is accepted without `--url` as a one-run override of a registered project's root ref (the
descriptor bridge needs it). Verification runs against a fresh checkout pinned to the branch
under review, never the canonical clone (Concrete Steps). Does not touch: projects other than
doperpowers (each adopts `devenv/` on its own schedule). Proves acceptance 8.

### M5 — sminos on hosts, and acceptance

At its end, the whole acceptance holds on one container and one throwaway VM. Touches
`devcloud/boot` step 11 (sminos daemon install, lingering, enable and start, for an enrolled
persistent host; sandbox identity hygiene) and `devcloud/README.md`.

Preflight, before any cloud resource exists: confirm M3's profile is pushed and its Secret Manager
entries populated; prepare the descriptor and mount the seed outside the repository; prove the
seed's token exchange reads the bootstrap secret; check that a container on the test machine
reaches tailnet peers through its host's route (Docker's masquerade should carry it; if not, the
container gets the host's network namespace and the deviation is logged); then request from the
person, through the dispatching session, a one-time tagged Tailscale auth key, and agree a window
for the enrollment step below so the VM does not wait unattended; and ask the ci-kit session
(`@doperpowers/CI-opt`) when its mac lane is measuring on the Mac mini, and run the acceptance
traffic through the mini's gateway outside those windows.

Run: acceptance 1–2 on a Mac (no Docker needed); acceptance 3, 5–6, 8 on a container run on the
throwaway VM, which has joined the tailnet, so the container reaches the gateway through its host
as a sandbox on a persistent host would — no Docker daemon is started on either Mac (Decision Log,
2026-10-17); then the VM itself (created with
the person's existing provider CLI, never in a cloud project ci-kit operates — ci-kit's agents
delete what they recognize there, and its spec asks that personal hosts live elsewhere):
acceptance 3–6 and the unenrolled half of 7; request the
person's enrollment of the VM; the enrolled half of 7 including its reboot; delete the VM the same
day and record it in Progress.

### Concrete Steps

Run from the devcloud worktree unless stated. `$DESC` and `$SEED` are paths outside the repository
(M5's preflight prepares the real ones; M2's tests generate their own).

    # M1
    devcloud/tests/mods/run.sh
    tests/mods/run-mods-tests.sh               # doperpowers' own mods, unchanged
    # M2
    devcloud/tests/run.sh                      # expect: every case "ok"
    docker build -t devcloud-test -f devcloud/image/Dockerfile \
      --build-arg DEVCLOUD_USER=<user> --build-arg DEVCLOUD_UID=<uid> --build-arg DEVCLOUD_HOME=<home> .
    # M2/M5 acceptance 3 (container)
    docker run -d --name sbx-test --hostname sbx-test \
      -v "$DESC":/etc/devcloud/boot.env:ro -v "$SEED":/run/devcloud/seed.json:ro devcloud-test
    docker exec sbx-test devcloud status       # expect: every step "ok"
    docker exec -u <user> sbx-test claude -p "reply ok"   # expect: ok
    # M3 (config repo)
    python3 -m unittest discover -s ~/.claude/tools/tests
    # M4: a fresh checkout pinned to the branch under review, never the canonical clone
    G=$(mktemp -d); DEVENV_GH="$G" devenv up doperpowers --ref devcloud
    DEVENV_GH="$G" devenv up doperpowers --ref devcloud   # second run: "unchanged, setup skipped"

### Interfaces and Dependencies

**I1 — Secret store** (unchanged from `cua`): `~/.config/claude-secrets/<KEY>` and
`~/.config/claude-secrets/projects/<slug>/<KEY>`, one value per regular file, mode 0600, directory
0700, one trailing newline dropped on read; keys `[A-Za-z_][A-Za-z0-9_]*`.

**I2 — Handles**: one per distinct redacted byte string, restored to exactly those bytes.

    [secret:KEY]                  the effective store value of KEY
    [secret:KEY@global]           a global value shadowed by a project-tier KEY
    [secret:KEY@<slug>]           another project's value of KEY (<slug>: that project's folder
                                  under the store's projects/); restores to that tier's value
    [secret:<file>:<field>]       a credential-file value (file basename, or its path from $HOME
                                  when two files share a basename; field: the path inside it)
    ...#<n>]                      a second distinct value under a label already taken (#2, #3, …)
    ...~<enc>]                    an encoded spelling of any of the above: ~b64, ~b64np, ~b64u,
                                  ~b64up, ~hex, ~HEX, ~url, ~json, ~pgpass (e.g. [secret:KEY~b64])
    [superseded:<label>]          a value <label> (any of the above) held earlier in this
                                  process; never restored
    [redacted:<kind>#<ns>.<n>]    a pattern detection; kind is the rule id (github-pat,
                                  anthropic, pem, assignment, ...); ns is 4 random base32
                                  characters drawn when the mod starts; n counts within ns

Restored in the inputs of Write, Edit, MultiEdit, NotebookEdit, and Bash: a known-value handle to
the credential's current value in the named spelling; a pattern handle only when this process
issued it. Anything else is left as written and named in the result. A label component writes
whitespace, `[`, `]`, `~`, `%`, and non-ASCII bytes as `%XX` (UTF-8), so every label round-trips.
In Bash only `command` is restored, and only an inert value in a plain string or plain word
(judged whole) of a plain command, as it is; every other handle stays, the result naming a read
that prints exactly its bytes in its place (§9.3); file tools get raw bytes.

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
exit 0 on success; safe to re-run; leading comment lines `# devenv-inputs: <glob> ...` name the
files whose change triggers a re-run), `devenv/start.sh` (optional; runs the project's services in
the foreground; `devenv start` runs it in tmux session `<name>`), `devenv/validate.sh` (optional;
`devenv validate` runs it), `devenv/env` (optional; `KEY=value` lines and
`secret:KEY=<Secret Manager id>` lines). Generated state stays under `.devbox/`, gitignored.

**I5 — Boot descriptor** `/etc/devcloud/boot.env`:

    DEVCLOUD_NAME=<host name>                  # unique; sandboxes sbx-<random>; a container's --hostname
    DEVCLOUD_KIND=vm|microvm|container
    DEVCLOUD_ROLE=persistent|sandbox           # persistent requires systemd as PID 1
    DEVCLOUD_TAILSCALE=join|host|none
    DEVCLOUD_TS_AUTHKEY_FILE=<path>            # join only; deleted after use
    DEVCLOUD_SEED=file:<path>|gce-metadata
    DEVCLOUD_SM_PROJECT=<GCP project id>
    DEVCLOUD_CONFIG_REPO=<https clone URL>
    DEVCLOUD_CONFIG_BRANCH=<branch>            # default main
    DEVCLOUD_CONFIG_TOKEN_SECRET=<Secret Manager id of the GitHub token>
    DEVCLOUD_PROJECTS="<entry> ..."            # optional; entry: <name>[@ref] | <owner>/<repo>[@ref]
    DEVCLOUD_MIRROR_DIR=<path>                 # optional; sandboxes: the host's mirror cache

**I6 — Status**: `/var/lib/devcloud/status.json`, `{"steps": [{"name", "state": "ok|failed|skipped|missing", "at", "detail"}]}`; `detail` never holds a value. `devcloud status` prints one line per step; a reconcile records its steps the same way.

**I7 — Services**: `pull-config` (30 min; reconciles on a new commit), `refresh-secrets` (30 min),
`session-mirror ship` (continuous), `sminos daemon` (enrolled persistent hosts only; its own
systemd user unit, enabled and started by boot). Under systemd: units named `devcloud-<service>`;
otherwise `devcloud-services` runs the first three.

**I8 — Profile** `~/.claude/devcloud/` (private): `managed-settings.json` (copied to
`/etc/claude-code/managed-settings.json`; its `env.ANTHROPIC_BASE_URL` is the gateway step 6
checks), `profile.env` (`KEY=value` lines appended to `/etc/devcloud/env`; `TZ` also sets the
system time zone), `secrets.toml` (I3), `build.env` (`DEVCLOUD_USER`, `DEVCLOUD_UID`,
`DEVCLOUD_HOME`, read where the image is built), `home/` (files copied into the user's home at
boot step 8 and every reconcile; secret-free).

**I9 — Guard marker** (devcloud sets it; `cua` reads it): from each session's start, the
session's `$.state` holds `{ owner: "devcloud", version: 1 }` under
`{ plugin: "devcloud", key: "secrets-guard" }`, typed in devcloud's contract
(`devcloud/types/devcloud.d.ts`, named as `types` in its `plugin.json`). Every plugin reads it
(`await $.state.get({ plugin: "devcloud", key: "secrets-guard" })`, at hook time); only devcloud
writes it; a `claude` started from a tool call has a session of its own and decides for itself.
Not a `globalThis` symbol, as first drafted: M1's check (2026-10-17, 2.1.302) found that the
engine evaluates each plugin's module in a realm of its own — a symbol devcloud's module set
read `undefined` from another plugin's module at hook time, while `$.state` read the value — so
`$.state` is the narrowest shared channel that stays out of child processes, and the ticket names
it. Limit: a session in which devcloud is disabled mid-way may keep the value (whether the engine
clears a plugin's state when it unloads is unverified).

## Surprises & Discoveries

- (2026-10-15) The GCP organization enforces `iam.disableServiceAccountKeyCreation`, and the
  person's owner service account cannot set organization policy (`orgpolicy.policy.set` absent at
  project and organization). No new service-account key can exist, so a read-only seed account is
  not available. Evidence: `gcloud resource-manager org-policies describe --effective`, and
  `testIamPermissions` on both resources.
- (2026-10-15) `sync/apply.py` exits 0 after failed plugin or MCP installs and prints each MCP
  server's configuration JSON in its command echo (reviewer's scratch-HOME probe; confirmed by
  reading the file).
- (2026-10-15) An attachment rewrite cleans the rendered text but the JSONL row keeps the original
  attachment payload; manual compaction rows bypass `session.append` (design review, from the
  engine bundle and `hooks/mods/README.md`).
- (2026-10-15) The `devenv` tool's install script already carries a `# devenv-inputs:` header, and
  its registry pins every project to an unmerged manifest branch.
- (2026-10-16) The engine writes an oversized tool output to the session's `tool-results/` before a
  hook sees the result, and the session store ships that directory once per file, treating it as
  immutable (round-2 review, from the 2.1.301 engine and `tools/session-mirror`).
- (2026-10-16) The shared MCP configuration (`sync/mcp.json`) holds one server and no secret value;
  the secret-bearing MCP servers are machine-local today.

- (2026-10-17) The engine evaluates each plugin's hooks module in a realm of its own: a
  `globalThis` symbol one plugin's module sets is not visible to another's, at load or at hook
  time; `$.state` is (two-plugin probe with `--plugin-dir`, 2.1.302).
- (2026-10-17) The transcript records the system prompt itself: `prompt_snapshot` attachment rows
  (`attachment.systemPrompt`) and `api-request-shape` rows (`shape.system`); text from
  `--append-system-prompt` is joined after the composed sections, where `prompt.compose` does not
  see it (boundary probe).
- (2026-10-17) After a compaction the engine attaches again, as `file` attachments with their full
  content, the files the model had read — a background command's output file among them — so an
  attachment payload is where values reach the transcript (boundary probe).
- (2026-10-17) `session.compact` hands a hook the compaction's instructions on the way down and the
  summary messages on the way up, both rewritable, so a manual compaction is covered even though
  its rows bypass `session.append` (d.ts of 2.1.300; boundary probe run 2).
- (2026-10-17) The auto-mode classifier reads the call as `tool.call` hooks left it: a Write whose
  content held a restored handle reached the classifier's request (a `claude-sonnet-5` call
  through the gateway, `{"Write":"<path>: <content>"}`) with the value in place, while the
  transcript it was shown carried earlier calls' handles. `tool.check` refuses a rewritten
  input ("the tool, its input and the call are the question and are pinned"). In the probe's
  sessions no classifier request appeared for `nc` or `python3 -c` commands, so which calls the
  mode sends to it is not settled (acceptance run, 2026-10-17).

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
- Decision: The seed is the person's existing gcloud service-account key (or, on GCE, that account
  attached to the VM), and it also becomes the user's gcloud identity and ADC.
  Rationale: the organization forbids new keys (Surprises), so the read-only seed account the
  first draft named cannot exist; the owner key was already on the host list, so using it as the
  seed widens nothing. Rejected: workload identity federation against an issuer the person runs
  (keyless, but a service to operate — deferred, Out of scope); a user OAuth refresh token (tied
  to a person's session policy).
  Date/Author: 2026-10-15, review round 1.
- Decision: The token exchange goes through `gcloud` against a root-private configuration, not a
  hand-written signer. Rationale: Google requires RS256 and the Python standard library cannot
  sign; `gcloud` is already in the image. Rejected: invoking `openssl` (works, but adds key-format
  handling the CLI already does).
  Date/Author: 2026-10-15, review round 1.
- Decision: The gateway is checked after the profile is read (step 6), and the profile names it
  once, in `managed-settings.json`. Rationale: the first draft probed it in step 2, before any
  input named it. Rejected: putting the gateway URL in the descriptor (a second place to change).
  Date/Author: 2026-10-15, review round 1.
- Decision: Containers receive their name through `--hostname`; boot verifies it. Persistent hosts
  require systemd. Rationale: Docker withholds `CAP_SYS_ADMIN`; the sminos daemon and reboot
  survival need systemd. Rejected: running `sminos daemon run` under `devcloud-services` (a second
  daemon lifecycle to maintain for a combination no driver needs yet).
  Date/Author: 2026-10-15, review round 1.
- Decision: `pull-config` reconciles (steps 5–11) when the commit moves. Rationale: a fetched
  profile change otherwise never reaches managed settings, which outrank every synced setting.
  Rejected: reconciling only at boot.
  Date/Author: 2026-10-15, review round 1.
- Decision: Hosts get no model credential; the secret inventory is reviewed by the person before
  upload, and exposed keys upload only after rotation. Rationale: the first draft listed a Claude
  token and an OpenRouter key for hosts, contradicting "the gateway holds every model credential".
  Date/Author: 2026-10-15, review round 1.
- Decision: Handles carry the exact-bytes identity (encoding, tier, file) and a per-process
  namespace for pattern detections; an unissued handle is written literally and named in the
  result. Rationale: one handle for several spellings or tiers restores the wrong bytes, and a
  per-session counter collides after a resume. Rejected: refusing a write that carries an unknown
  handle (contradicts redact-never-refuse and would block writing the mod's own tests).
  Date/Author: 2026-10-15, review round 1.
- Decision: The mod's guarantee is the list of paths its hooks reach, established by a boundary
  probe at the start of M1. Rationale: attachments, manual compactions, and the system prompt do
  not pass through the hooks the first draft relied on. Rejected: promising "neither the API nor
  the transcript ever sees a value".
  Date/Author: 2026-10-15, review round 1.
- Decision (superseded 2026-10-16, below): The cutover from `cua`'s mod is staged — the new mod
  released, installed, and verified before `cua`'s removal ships. Rationale: the reverse order
  leaves a window with no guard; the old mod's deny path makes the overlap strict, not unsafe.
  Date/Author: 2026-10-15, review round 1.
- Decision: `/secret` stays in `cua`; devcloud carries only the guard, and `cua`'s guard stands
  down when devcloud's is loaded. Rationale: the person uses `/secret` with `cua`'s GUI and browser
  typing, so `cua` must keep it on its own; one guard must decide each handle. Rejected: moving
  `/secret` into devcloud (breaks `cua` alone); both plugins registering `/secret` (two commands,
  two panes); both guards running (refusals contradict redaction, and a second scrubber loses the
  encoding a handle names). Supersedes the staged-cutover entry: nothing is removed from `cua`, so
  either release order is safe.
  Date/Author: 2026-10-16, the person's correction.
- Decision: `cua` installed alone drops its refusals and keeps scrubbing stored values.
  Rationale: the refusals were the strictness that prompted this work (they refuse even a command
  that only writes the store's path as text), and scrubbing at the output already catches a
  printed value. Rejected: keeping `cua` alone strict as today.
  Date/Author: 2026-10-16, the person's choice.
- Decision: `cua`'s half is a ticket for the `cua` project, filed as soon as M1's marker (I9) is
  merged; this initiative does not edit `cua`. Rationale: `cua` has its own project and session,
  which know its tests and release; this work only has to define the contract. Filed after M1
  rather than at the end so `cua` stays strict for days, not for the whole initiative. Cost of the
  interim: both guards run when both are enabled, so `cua` still refuses store commands and may
  collapse an encoded stored value's handle to `[secret:KEY]`; M1 proves its acceptance with `cua`
  disabled and the both-enabled run waits for the ticket.
  Date/Author: 2026-10-16, the person's proposal; filing after M1 rather than at the end is the
  design session's refinement.
- Decision: M2 proves the boot core with no projects; acceptance 3 in full runs in M5. Boot steps
  run strictly in order. Rationale: the project runner is M4's; `apply.py` creates the link step
  12 calls.
  Date/Author: 2026-10-15, review round 1.
- Decision: The `devenv` runner keeps its commands and generated state; `devenv/` replaces only the
  manifest; per-service windows, readiness probes, the linked start skill, and sandbox settings
  retire. Descriptor entries map to registry names or `owner/repo`, with `@ref` overriding.
  Rationale: the person's everyday launch paths must survive the change of declaration format.
  Date/Author: 2026-10-15, review round 1.
- Decision: Coordination with ci-kit (the person's CI initiative, `SSFSKIM/ci-kit`) is limited
  to four points: devcloud's suites become gates in doperpowers' `.github/ci-kit.yml`; the
  `devenv` skill reads a repository's `ci-kit.yml` first; M5's VM stays out of ci-kit's cloud
  projects; and devcloud's acceptance traffic through the Mac mini's gateway avoids ci-kit's mac
  lane measurement windows, which the CI-opt session names when asked. Rationale: the two meet at
  a repository's install path and at shared machines, not in their images or launchers — ci-kit's
  runner image and VMs deliberately carry no credentials and no service account for untrusted
  job code, devcloud's carry the person's, so sharing either would weaken one or burden the
  other. Deferred, to propose to CI-opt after M4: a ci-kit `setup` that runs `devenv/setup.sh`,
  so a repository states its install once for both. Later, a devcloud provisioning driver for GCE
  spot starts from ci-kit's launcher (`lib/gce.mjs`: zone fallback, `maxRunDuration` deletion).
  Date/Author: 2026-10-17, design session, on the person's question.
- Decision: Packaging. The secrets mod, the `devenv` skill, and the host image and boot program
  ship as a second plugin, `devcloud`, in the doperpowers repository and marketplace, versioned on
  its own; doperpowers stays the workflow plugin.
  Rationale: the mod changes what the model sees in every session, which a person installing
  doperpowers for its workflow should opt into; host and redaction changes then release without
  moving doperpowers. Rejected: everything in doperpowers (one version, but redaction imposed on
  every doperpowers user); a separate repository (another repository and marketplace for no gain).
  Date/Author: 2026-10-15, the person's choice on the recommendation.
- Decision: The image's user, uid, and home are build inputs from the profile. Rationale: public
  mechanism, private values; a person whose Mac account differs gets the same guarantee.
  Date/Author: 2026-10-15, review round 1.

- Decision: A known-value handle (`[secret:KEY]`, a credential-file label) restores to the
  credential's current value, in any process; a value superseded within the process reads
  `[superseded:…]` and never restores; only pattern handles are bound to the process that issued
  them. Rationale: the handle is the name the system prompt teaches (`Bearer [secret:KEY]`), so it
  must mean the same thing across sessions; after a rotation the current value is what a command
  or a written file needs, and an Edit against stale bytes fails visibly at its match. Rejected
  (round-2 finding): a process-unique identity for every known value, which would make a key's
  handle unusable in the next session.
  Date/Author: 2026-10-16, review round 2.
- Decision: Oversized outputs persisted to `tool-results/` are scrubbed in place by the mod before
  the call returns, and the session store waits a settle interval before shipping such a file.
  Rationale: the session store copies that directory to the central database and the archive.
  Rejected: listing them as not covered (the largest outputs are the likeliest to carry a
  credential file's contents); scrubbing in the session store (it would have to know the secrets).
  Date/Author: 2026-10-16, review round 2.
- Decision: The kill window between the engine persisting an oversized output and the mod
  rewriting it is a stated limit, not closed. Rationale: the window is the hook's own synchronous
  continuation, so it needs a process kill at that instant; the copy it would leak goes to the
  person's own private store. Rejected (round-3 finding): a scrub-complete marker the session
  store checks before shipping, which couples the store to the mod for that instant. Tracked in
  `docs/doperpowers/TECH-DEBT.md` with its trigger.
  Date/Author: 2026-10-16, review round 3.
- Decision: No secret in a command line from `apply.py`: shared MCP configs carry `${VAR}`
  references, verified to expand at user scope before relying on it.
  Date/Author: 2026-10-16, review round 2.
- Decision: Hosts get the person's git identity, global git settings, tmux configuration, and a
  host-safe zsh rc from the profile's `home/`, and zsh as the login shell. Rationale: commits on a
  host need the identity, and "works like the Mac" includes the shell; the Macs' own rc files carry
  exported keys, so a separate host-safe rc is kept rather than copying them.
  Date/Author: 2026-10-16, from the person's question about what the setup covers.
- Decision: Execution pre-flight. The branch was rebased onto origin/main at 7.164.1, where the
  marketplace already lists a second plugin (`ci-kit`, a URL source with no version), so devcloud's
  marketplace entry is the third; "second plugin" in this spec means "a plugin besides
  doperpowers". Version bumps and the manifest tests address a plugin by its `name`, never by its
  index, so a later reorder cannot move the wrong version. M1 ships as its own pull request to
  main (the spec plus M1), released before M2 starts; M2–M5 continue on `devcloud` after it
  merges. Rationale: the dispatching session's brief (M1 must reach the Macs early); addressing by
  name follows from a marketplace whose order this work does not own.
  Date/Author: 2026-10-17, plan executor.

- Decision: The guard marker (I9) is a `$.state` value, not a `globalThis` symbol, set at
  `session.start`. Rationale: plugin modules do not share a realm (Surprises, 2026-10-17);
  `$.state` is session-scoped, readable by every plugin, writable only by its owner, and absent
  from a child `claude`. Rejected: an environment variable (child processes inherit it); a file
  (shared by every process on the machine).
  Date/Author: 2026-10-17, M1 executor.
- Decision: The auto-mode classifier's request stays on §9's not-covered list, and handles keep
  restoring in Write and Edit. Rationale: the guard keeps values out of the conversation's context
  and out of stored copies; the classifier's request is neither — it goes only to the provider,
  through the person's own gateway, and only after the model deliberately wrote a handle.
  Rejected: rewriting a Bash call's store handle to a `$(cat …)` read (breaks inside single
  quotes, covers store handles only, and Writes would still carry the value); not restoring
  handles under auto mode (breaks editing a redacted file).
  Date/Author: 2026-10-17, the person, through the design session.
- Decision: No Docker daemon is started on either Mac. M2's container tests run on ci-kit's hosted
  Ubuntu runner (the `devcloud` gate); M5 runs the container acceptance on the throwaway VM, which
  joins the tailnet, so its container reaches the gateway as a sandbox on a persistent host
  would. A wall in that plan goes to the design session before any fallback to a Mac.
  Rationale: the MacBook's load is what ci-kit moves off it, and Docker.app may ask for a
  privileged helper, which the person's privilege rule stops at.
  Date/Author: 2026-10-17, the design session.
- Decision: M1 review fixes widen I2: other projects' tiers are loaded and redacted
  (`[secret:KEY@<slug>]`), labels are `%XX`-encoded, a colliding label takes `#<n>`, `~pgpass`
  joins the encodings, and a Bash restoration quotes the value for its shell context. An unquoted
  assignment value with no digit reads as a code reference and is not redacted. Rationale:
  removing `cua`'s refusal of other-project reads needs redaction in its place; raw substitution
  into a shell let a value's metacharacters run; ordinary auth code (`process.env.API_KEY`) must
  stay readable. Cost accepted: a digit-free unquoted random value (about 1.5% of 24-character
  alphanumerics) is missed by the assignment rule; quoted values and prefixed tokens are still
  caught.
  Date/Author: 2026-10-17, M1 fix wave 1 (task and high-rung reviews).
- Decision: M3's profile. The gateway URL in `managed-settings.json` is the gateway machine's
  tailnet HTTPS name (the relay listens on loopback and is published to the tailnet by
  `tailscale serve`); `profile.env` sets `LANG=C.UTF-8` (Ubuntu ships no other UTF-8 locale until
  one is generated). `apply.py` refuses a shared MCP server that carries a literal credential,
  counting it as a failed operation, and skips a plugin whose directory marketplace the machine
  lacks rather than failing. `${VAR}` expansion at user scope was verified (2.1.302) for HTTP
  headers and stdio env; no shared server needs it yet. The profile's `home/` is nested
  (`.config/…`), so boot copies it recursively; its `.gitconfig` requires git-lfs, so the image
  installs it. Secret Manager uploads are run by the person: the auto-mode classifier refuses an
  agent's script that reads credential sources and writes a secret store, and that refusal is
  not routed around.
  Date/Author: 2026-10-17, M3 executor and plan executor.
- Decision: Bash restoration is safe by construction rather than context-aware. An inert value
  (only characters no bash or zsh context treats specially) restores raw anywhere; a non-inert
  value restores only inside a plain single- or double-quoted string or an unquoted top-level word
  of a command with no backtick, heredoc, here-string, nested expansion, comment, or line
  continuation; any other handle stays unrestored and its result names it, pointing to
  `"$(cat …)"`. Rationale: fix wave 1's context-aware quoting leaked through here-strings,
  heredoc bodies and delimiters, backticks, comments, and zsh's `=` expansion — each a way for a
  value's bytes to run as code. Leaving a handle unrestored is redaction, not refusal: the
  command runs. Rejected: patching each shell form (an open set).
  Date/Author: 2026-10-17, plan executor; confirmed by the design session.
- Decision (narrows the entry above): In a Bash command only an inert value is ever restored, and
  only at a plain position (plain neighbors; never after `$`, `$name`, `==`, `:=`) in a plain
  command (no heredoc or here-string, backtick, arithmetic — `((`, `$[`, `let`, `[[`, integer
  declarations — comment, or continuation). A non-inert value is never restored into a command;
  the context-quoting code is deleted. Every unrestored handle's notice names a read that works
  for its kind: the store file, the credential file and field (`jq -r` for JSON), the encoding
  step for an encoded spelling, and for a pattern handle a temp file written with a file tool.
  Rationale: the proved-context quoting leaked again in the third review (escaped handle starts,
  arithmetic contexts), and each round found a new construct; a whitelist of positions with an
  execution matrix over seven shell variants is checkable, and the notice keeps every handle
  usable. Rejected: further lexer patches.
  Date/Author: 2026-10-17, plan executor; confirmed by the design session.
  Amended (fix wave 4, same day): positions are judged by the whole word or quoted string that
  holds the handle, not by its two neighbors — inside `'…'`; inside `"…"` with no `$`, backtick,
  `\` or `!`; or in an unquoted word of inert characters that does not start with `=` or follow a
  redirection — after zsh's `$name:` modifiers, word-initial `=`, float and subscript arithmetic,
  and `${X/…}` changed bytes silently under the neighbor rule. Notices give exact reads that keep
  trailing newlines, decode each credential file's own escaping, and name each `#n` entry; they
  assume `python3`, `jq`, `perl`, `xxd`, and `gh`, which the image installs. Padded base64 inside
  a URL word stays unrestored.
- Decision: Acceptance 6 checks what it is for — no credential and no per-host input in the
  image — in three parts (known values, credential files and `boot.env`, pattern detections outside
  package-owned trees), since the pattern detector flags about 15,000 vendored strings in about
  1,800 package files (M2). The image user gets passwordless sudo: a project's `devenv/setup.sh`
  installs system packages, the cloud images' default user has it, and the host already holds the
  person's credentials. Root's shells do not load `/etc/devcloud/env`, which can put
  user-writable directories on root's `PATH`.
  Date/Author: 2026-10-17, the design session on the plan executor's proposal.

## Outcomes & Retrospective

Pending — written at finish. Interim, at M1's pull request (2026-10-17): the guard's hardest
part was not detection but restoring handles into shell commands. Four review rounds each found a
shell construct (here-strings, heredoc delimiters, backticks, arithmetic, zsh modifiers and equals
expansion) where substituted bytes stopped being data; the design converged only when restoration
was narrowed to inert values in whole words or quoted strings the guard can classify, with every
other handle left in place and its notice naming an exact read. Two reviewers on the gateway's
frontier model were stopped by provider safety filters while probing shell injection; the last
verification ran their reproduction set and a plausible-shapes matrix directly.
