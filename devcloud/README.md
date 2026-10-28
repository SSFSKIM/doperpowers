# devcloud

A second plugin in the doperpowers marketplace, installed on its own
(`claude plugin install devcloud@doperpowers`): doperpowers stays the
workflow plugin, and a person opts into devcloud. It carries the secrets
guard, the host image and boot program that make any Linux userland work
like the person's Mac, and the `devenv` skill that writes a repository's
`devenv/` (design: `docs/doperpowers/specs/2026-10-15-devcloud-design.md`).
It also carries the VM driver, `devcloud vm`, which makes such hosts on
cloud machines and deletes them when their lease ends, and the `vm` skill,
which tells a session when a VM is worth it, what needs the person's yes,
and how to add a cloud (design:
`docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`).

## The secrets guard (`hooks/mods/secrets.tsx`)

A mod (a function hooks module, loaded under
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`) that keeps secrets out of what the
model reads and what the transcript keeps. It redacts and never refuses: no
tool call is denied for touching the secret store, so `cat`, `ls`, `mv`,
`test -f` and writes there all run, and a value a command prints is caught
in its output.

**What it knows.** Three sources, read again whenever a file changes:

- the values stored through `cua`'s `/secret` (`~/.config/claude-secrets/KEY`
  for every project, `~/.config/claude-secrets/projects/<slug>/KEY` for one;
  one trailing newline dropped), the session's project being the main checkout
  of the git repository around it; every other project's tier is read too, as
  a command can print any of them;
- the secret fields of well-known credential files under `$HOME`: gh's
  `hosts.yml`, `~/.pgpass`, gcloud's service-account and authorized-user key
  files under `~/.config/gcloud/`, `~/.codex/auth.json`,
  `~/.claude/.credentials.json`, hcloud's `cli.toml`, `~/.docker/config.json`'s
  auths, `~/.netrc`, `~/.git-credentials`, `~/.npmrc`;
- token-shaped strings anywhere (`hooks/mods/secrets-detect.tsx`, a pure
  `detect(text)`): published prefixes after gitleaks' rules (`sk-ant-`,
  `sk-or-v1-`, `sk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`,
  `tskey-`, `xox[abprs]-`, `AKIA`/`ASIA`, `glpat-`, `hf_`, `AIza`), PEM
  private-key blocks raw or JSON-escaped, and assignments whose name says
  secret (`TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`, `APIKEY`,
  `PRIVATE_KEY`, `BEARER`, `CREDENTIAL`, any case, as a whole part of the
  name split at `_`, `-`, `.` or a camelCase boundary; `Bearer <value>` too)
  whose value is at least 16 characters of at least 3.5 bits of entropy per
  character and, unquoted, is no code reference (a dotted name such as
  `process.env.API_KEY`, a digit-free identifier, a call or an index). Bare hex or base64 is never a token: commit hashes and checksums
  stay readable.

### Keep installed-package source readable

Build an original-content index explicitly after installing or updating global
npm packages or the gcloud SDK:

```sh
devcloud guard index --fetch
devcloud guard status --json
```

`--fetch` downloads public exact-version checksum metadata and artifacts.
Without it, `devcloud guard index` rebuilds offline from cached evidence. The
command runs as your ordinary user on macOS and Linux; it installs no daemon,
timer or automatic refresh. Status reports verified coverage and skipped-reason
counts, not source values. Missing evidence is a coverage loss, not an error in
your installation.

For a supported native text **Read**, the guard compares the current file with
its publicly distributed bytes and binds that evidence to this call's source
slice. Generic secret-named constants then stay readable in both the tool
result and its transcript row. Stored values, credential-file values,
provider-shaped tokens and private keys are still redacted. Partial Reads are
supported. Automatic pagination retains its companion notice when the result
needs no redaction; rewritten Reads retain the existing notice-loss limitation.

This is not a package-directory allowlist. Modified or newly generated files,
project dependencies, caches, linked checkouts, unpublished packages and native
binaries receive full detection. Reindexing does not adopt local changes as
original contents. Missing/stale evidence, unsupported text, files above 16 MiB,
a missing Python interpreter, verification timeout or saturation all fall back
to normal scrubbing without refusing a successful Read. Verification is local,
shares a 1.5-second deadline, and never fetches or unpacks an artifact in a hook.

The exemption expires with its one matching appended result; it does not follow
text into Bash, notes, assistant prose, compaction or a resumed session. The
index stores metadata and digests in `$XDG_CACHE_HOME/devcloud/guard-provenance/v1`
when an absolute XDG override is set, otherwise the ordinary user cache area.
Python 3.9+ suffices for the standalone helper at
`hooks/mods/secrets-provenance.py`; the devcloud CLI retains its own Python
requirement.

For an aggregate utility report (Bun required), run
`devcloud guard index --fetch --report-corpus`, or
`devcloud guard report-corpus` to measure the existing index without rebuilding.
It reports detector matches, indexed original-byte equality, and preservation
through the production tool/append hooks separately. It reads no credential
sources and prints no paths or matched values. Its supported offset/limit
pages are at most 64 KiB; overlong lines and other fallbacks remain in the loss
counts. Credential protection is tested separately. The offline native probe,
`python3 -I devcloud/tests/mods/provenance_probe.py --engine /path/to/claude`,
uses synthetic fixtures and loopback-only networking; currently its OS network
sandbox requires macOS. Linux native acceptance is not claimed.

**Handles.** Each distinct redacted byte string gets its own:

    [secret:KEY]                  a stored value (the project's, where both tiers hold KEY)
    [secret:KEY@global]           a global value a project key of the same name shadows
    [secret:KEY@<slug>]           another project's value (<slug>: its folder under projects/)
    [secret:<file>:<field>]       a credential file's value (the file's basename, or its
                                  path from $HOME where two files share one)
    ...~<enc>]                    an encoded spelling of any of those: ~b64, ~b64np (no
                                  padding), ~b64u, ~b64up, ~hex, ~HEX, ~url, ~json,
                                  ~pgpass (`\` and `:` backslash-escaped)
    [superseded:<label>]          a value a label held earlier in this process
    [redacted:<kind>#<ns>.<n>]    a pattern detection; <ns> is drawn when the module loads

In a label, whitespace, `[`, `]`, `~` and `%` are written `%XX`, so every label
round-trips; a second distinct value under a label already taken (two
credentials one parser names alike) is `<label>#2`, `#3`, ..., never dropped.

Before a Write, Edit, MultiEdit, NotebookEdit or Bash call runs, each handle
in its input is replaced by its bytes: a known handle by the credential's
current value in the named spelling, a pattern handle by exactly the bytes
it replaced, if this process issued it. So a file edited through a handle
keeps its secret, and `Authorization: Bearer [secret:KEY]` in a command works
like `"$(cat ~/.config/claude-secrets/KEY)"`. In a Bash command (its `command`
only) a handle is restored only where that is shown safe, and never quoted: an
inert value (`[A-Za-z0-9_./+:@-]`, `=` and `%` past the first character, no `=`
right after `=` or `:` but in a trailing run: most tokens and base64), standing
in a plain string or word: inside `'…'`, inside a `"…"` with no other `$`,
backtick, `\` or `!`, or in an unquoted word made only of that alphabet and
inert as a whole, not a redirection's target. The command must hold no heredoc
or here-string, backtick, `${`, arithmetic (`((`, `$((`, `$[`, `[[`, `let`,
`integer`, `float`), flagged declaration, comment or line continuation. So
`"Authorization: Bearer [secret:K]"`, `--token=[secret:K]`, `X=[secret:K] cmd`
and `https://user:[secret:K]@host` work. Every other handle stays, and the
result gives one line per handle with a read that prints exactly the value:
`"$(cat <store file>)"` for a store key, `jq -j` for a JSON field, `gh auth
token` for gh's hosts file, a `python3` read that undoes the file's escaping for
TOML, `.pgpass`, `.netrc`, `.git-credentials` and `.npmrc`, that read piped into
its encoding for an encoded spelling, a pipe or `<(…)` for a value ending in a
newline, and for a pattern handle a file tool writing it to a temporary file to
`cat`. `tests/mods/shell-exec.ts` proves it by running the restored commands
under bash and zsh, with their word-reading options, and each read against real
files. File tools get the bytes raw. A handle that cannot be
restored — `[superseded:…]`, a key no longer stored, another process's (or a
resumed session's earlier) pattern handle — is written as is, and the tool's
result carries a line naming it. The transcript keeps the call as the model
wrote it, handles and all. One system-prompt section tells the model this.

**Where it reaches** (the guarantee): a tool's result as the model reads it
and as the transcript keeps it (`toolUseResult`), in the main loop and in
subagents; every row appended to the conversation (the person's prompt, a
background command's notification, a subagent's result); an oversized
output's file in the session's `tool-results/`, rewritten before the call
returns (in place, or past 4 MiB through a `.tmp` file renamed over it) (the session store ships such a file only once it has held
still for 3 s); the system prompt's composed sections; the first message's
context blocks (`CLAUDE.md`); each attachment's text as a request carries
it; a compaction's instructions and its summary.

**Where it does not** (probed 2026-10-17 on Claude Code 2.1.302):

- an attachment row's own payload in the transcript file: a changed file the
  model had read, and the files the engine attaches again after a compaction
  (a background command's output file among them), keep their content there
  beside the scrubbed text the model reads, so the session store's copy holds
  it too;
- system-prompt text given with `--system-prompt` or `--append-system-prompt`,
  which the engine adds after composing the sections: every request carries
  it, and the transcript's `prompt_snapshot` and `api-request-shape` rows keep
  it;
- a background command's own output file in the engine's temporary
  directory (local, never shipped; the model reads it only through a tool,
  scrubbed);
- the call a restored handle runs in: the permission dialog shows it; in
  auto mode, a call the mode sends to its classifier is judged with its
  values in place, and the classifier is a model request of its own (observed
  for a Write; the permission check's input is pinned, so no hook can hand it
  the handles); and a command's arguments are visible to the machine's other
  processes while it runs;
- where an organization manages Claude Code, a plugin a person installs does
  not get `prompt.compose`, `prompt.context`, `prompt.attachment` or
  `session.compact`: the system prompt, context blocks, attachments and
  compactions are then not covered;
- a value the model slices, reverses or transforms on purpose; a secret
  inside an image; an oversized output whose process is killed between the
  engine writing it and the guard rewriting it.

**With `cua`.** `/secret` — the command, its masked pane, the store and the
system-prompt section listing the stored keys — stays in `cua`, and so does a
vendored copy of this guard, which acts when devcloud's does not. devcloud's
guard marker (`{ plugin: 'devcloud', key: 'secrets-guard' }` →
`{ owner: 'devcloud', version: 1 }`, typed in `types/devcloud.d.ts`) is the
loaded module's own answer to a `$.state.get`, at version 0, and never a
value the host stores: any plugin in the session reads it while devcloud's
module is loaded, whichever of the two sits outside the other, and nothing
once devcloud is disabled and the plugins are reloaded. `cua`'s copy stands
down only on that answer, so one guard decides every handle, and from the
reload on `cua`'s acts. (A stored marker outlived the module, and no guard
acted, until 0.5.0. A `globalThis` symbol does not work: the engine evaluates
each plugin's module in a realm of its own. A `claude` a tool call starts has
a session of its own.)

## The host (`image/`, `boot/`)

Any Linux userland — a VM, a microVM, a container — becomes a host on which
Claude Code works as on the person's Mac by running one program,
`devcloud-boot`, as root at every boot. It reads one input, the boot
descriptor, and converges: running it again never duplicates anything. What
is personal (the user, the gateway, the secrets map) lives in the person's
private configuration repository, the profile; this directory holds only
mechanism.

**The image.** `image/setup.sh` (root, Ubuntu 24.04, x86_64 or arm64)
installs what every host has — git and git-lfs, build tools, Python 3 with
venv, uv, Node LTS, jq, tmux, mosh, gh, the Google Cloud CLI, hcloud,
Tailscale, the Docker client, zsh, perl and xxd (with python3, jq and gh,
the tools the guard's notices suggest for reading a file), poppler's
`pdftotext` and a headless Chromium (the `web` plugin's fetch tool extracts
PDFs' text and renders pages that need their scripts with them), and Claude Code (native installer, as the
user) — and creates the user from three build inputs, `DEVCLOUD_USER`,
`DEVCLOUD_UID` and `DEVCLOUD_HOME`, the Mac's own account, so a session
moves between a Mac and a host under the same paths, with passwordless sudo
(a drop-in checked by `visudo`), as cloud images give their default user: a
project's `devenv/setup.sh` installs system packages. It carries no
credential, no descriptor, no `~/.claude` checkout and no sminos enrollment,
which `tests/check_image.py` checks in three parts: (a) none of a list of
known values — made-up ones in the tests, the person's own from their secret
store and Secret Manager when they run it — appears in any byte of the
image's files (binaries and files of any size included) or `docker history`, in any spelling the guard scrubs (the values go to the
guard's matcher in-process and are never printed); (b) none of the
credential files the guard reads exists under any home, nor the secret
store, nor the boot descriptor; (c) the guard's pattern detector finds
nothing outside package-owned trees (unchanged dpkg files, npm's
`node_modules`, the Claude Code and gcloud install trees, whose vendored code
matches token shapes by the thousand). Each part fails closed: a step of the
check that fails — the export, a scan that errs or reads nothing, a package
tool that fails rather than list differences — fails the check.

    # needs Docker and bun; prints parts, paths and labels, never a value
    python3 devcloud/tests/check_image.py <image> --home <home> --store <secret store dir> --values - < values.json
A VM builder runs `setup.sh` and snapshots, and its `devcloud-boot.service`
runs the boot at every start. `setup.sh` starts with `image/packages.sh`,
the packages and tools, which takes no input; `image/Dockerfile` runs its
four parts (apt, gcloud, tools, chromium) as a layer each, keyed on `packages.sh` alone
so that a change anywhere else in `devcloud/` reuses them from a build cache,
whose layers a warm build pulls side by side. `image/fetch-claude.sh` gets its
own script-only layer: it downloads the native release for the image's
architecture from Anthropic's release service and verifies its SHA256 against
`manifest.json`. Then `setup.sh` runs with no network (`DEVCLOUD_PACKAGES=installed`).
It seeds the verified binary in the user's native versions directory and runs
that binary's `install VERSION`; the native installer owns the launcher and
configuration, and the user's updater remains enabled. VM bakes and adopt run
the same fetch before setup; a failed fetch or checksum fails the recipe.

The weekly CI cache refreshes the release alongside the packages. During a
release-service outage, a warm build reuses the download layer even when other
`devcloud/` files change; a cold build still needs the release service and fails
loudly if it cannot fetch. `DEVCLOUD_CLAUDE_RELEASE_URL` overrides the release
base URL when running `fetch-claude.sh` (for example, a refusing test endpoint).

    docker build -t devcloud -f devcloud/image/Dockerfile \
      --build-arg DEVCLOUD_USER=<user> --build-arg DEVCLOUD_UID=<uid> --build-arg DEVCLOUD_HOME=<home> .
    docker run -d --name <name> --hostname <name> \
      -v "$DESC":/etc/devcloud/boot.env:ro -v "$SEED":/run/devcloud/seed.json:ro devcloud

A container cannot set its own host name, so the driver passes
`--hostname` and the boot only checks it. A sandbox reaches the gateway
through its host's tailnet (`DEVCLOUD_TAILSCALE=host`), and the gateway's
tailnet name resolves only through the tailnet's resolver, so on such a host
the driver also passes `--dns 100.100.100.100`. Its entrypoint runs
`devcloud-boot`, then `exec devcloud-services` when the boot exited 0 or 3
(below): any other failure ends the container, and
`docker run --restart on-failure` retries it from the top.

**The boot descriptor**, `/etc/devcloud/boot.env`, the only per-host input
(unknown keys are refused):

    DEVCLOUD_NAME=<host name>                  # unique; sandboxes sbx-<random>; a container's --hostname
    DEVCLOUD_KIND=vm|microvm|container
    DEVCLOUD_ROLE=persistent|sandbox           # persistent requires systemd as PID 1
    DEVCLOUD_TAILSCALE=join|host|none          # a sandbox never joins
    DEVCLOUD_TS_SECRET=<Secret Manager id>     # join: the Tailscale OAuth client (tag:devcloud)
    DEVCLOUD_TS_AUTHKEY_FILE=<path>            # join, the fallback: a one-time key; deleted after use
    DEVCLOUD_SEED=file:<path>|gce-metadata
    DEVCLOUD_SM_PROJECT=<GCP project id>
    DEVCLOUD_CONFIG_REPO=<https clone URL>
    DEVCLOUD_CONFIG_BRANCH=<branch>            # default main
    DEVCLOUD_CONFIG_TOKEN_SECRET=<Secret Manager id of the GitHub token>
    DEVCLOUD_PROJECTS="<entry> ..."            # optional; <name>[@ref] | <owner>/<repo>[@ref]
    DEVCLOUD_MIRROR_DIR=<absolute path>        # optional; sandboxes: where the host's mirrors are mounted
    DEVCLOUD_MAWS_SECRET=<Secret Manager id>   # optional, persistent: MAWS's provisioning code (step 13)
    DEVCLOUD_MAWS_DELEGATION_ID=<32 hex>       # with it: the delegation the machine's ref is minted under

The seed is a Google Cloud service-account key file the driver mounts (or,
on GCE, the VM's attached account through the metadata server). The boot
activates it into a root-private gcloud configuration
(`/var/lib/devcloud/gcloud`) and reads Secret Manager over its REST API with
the tokens it gives; it also becomes the user's gcloud identity and
application default credentials.

**The boot**, each step recorded in the status file; a failed step stops the
boot with the step named, and the next run starts again from the top:

| # | step | what it does |
|---|---|---|
| 1 | `identity` | refuses `persistent` without systemd as PID 1; sets the host name (VM) or checks it (container); writes `SESSION_MIRROR_HOST`, `MAWS_DELEGATION_ID` when the descriptor names one, and for a container a `DAEMON_BOOT_ID` of its own, fresh at each container start |
| 2 | `seed` | activates the seed and takes an access token |
| 3 | `bootstrap-secrets` | reads the GitHub token `DEVCLOUD_CONFIG_TOKEN_SECRET` names, and the Tailscale OAuth client `DEVCLOUD_TS_SECRET` names |
| 4 | `tailnet-attach` | `join`, unless the node is already joined: `tailscale up --advertise-tags=tag:devcloud` with the OAuth client as its auth key (tagged, pre-authorized; ephemeral while the host has a lease, and rejoined as the other kind when the lease changes, the VM driver's §4.1), handed over as `--auth-key=file:<root-only file>` and deleted after, never in an argument list; or, the fallback, with the auth key file, which is deleted |
| 5 | `configuration` | as the user, clones or fetches and resets `~/.claude`; the token reaches git through a credential helper reading a root-owned file the user's group can read, deleted after the fetch — never a URL or `.git/config`; then reads the profile |
| 6 | `tailnet-check` | the gateway named in the profile's managed settings answers |
| 7 | `secrets` | materializes `secrets.toml` |
| 8 | `home` | as the user: copies the profile's `home/`; the seed as gcloud's account and ADC, the Secret Manager project as gcloud's default; `gh auth setup-git` when gh has a `hosts.yml` |
| 9 | `apply` | runs the configuration's `sync/apply.py` as the user |
| 10 | `settings-and-env` | writes `/etc/claude-code/managed-settings.json` and `/etc/devcloud/env`; `TZ` sets the system time zone |
| 11 | `services` | installs or starts the services; restarts one whose unit or environment changed; on a persistent host that is a sminos machine, the sminos daemon (below); refuses a sandbox that carries a sminos machine identity |
| 12 | `projects` | `devenv up` per `DEVCLOUD_PROJECTS` entry, as the user; `skipped` when none (see "Projects") |
| 13 | `maws` | provisions MAWS's endpoint with the code `DEVCLOUD_MAWS_SECRET` names; `skipped` without it or without `mawsd`, `deferred` while its certificate is not yet listed (see "MAWS's endpoint") |

`devcloud-boot` exits 0 when every step is `ok`, 1 when a step of 1–11
failed, and 3 when the host is made and only step 12 or 13 failed: the host works
without a project, so the container entrypoint starts its services on 3 as on
0, and the boot unit counts 3 as success (`SuccessExitStatus=3`) so the units
ordered after it start. A driver sees a non-zero exit, the step records which
project failed, and `devcloud status` exits 1.

**Projects.** A repository describes its own environment in `devenv/` at its
root (the `devenv` skill writes it):

- `setup.sh` (required) installs its dependencies, on macOS and Ubuntu, and
  is safe to re-run; run as the user from the repository root. Leading
  `# devenv-inputs: <glob> ...` lines name the files (lockfiles) whose change
  makes it run again.
- `start.sh` (optional) runs the project's services in the foreground;
  `devenv start` runs it in tmux session `<name>`.
- `validate.sh` (optional) is the quickest real check that the environment
  works; `devenv validate` runs it.
- `env` (optional) holds `KEY=value` lines and `secret:KEY=<Secret Manager id>`
  lines, never a value.

The runner is the person's `devenv` (in their configuration repository, linked
to `~/.local/bin/devenv` by its apply step). Step 12 bridges each descriptor
entry to it: `<name>` runs `devenv up <name>` against the person's registry;
`<owner>/<repo>` runs `devenv up <repo> --url https://github.com/<owner>/<repo>.git`;
`@<ref>` on either adds `--ref <ref>`, which picks the ref for this host's
clone. Every entry is tried, with the user's login environment and
`/etc/devcloud/env`; the output goes to `/var/log/devcloud/projects.log`. A
reconcile does not run projects; `devenv up` is run when the work needs it.

**The mirror cache.** A persistent host keeps a bare mirror of each GitHub
repository of its projects at `/srv/devcloud/mirrors/<owner>/<repo>.git` (the
user's), made at step 12 and fetched by the `refresh-mirrors` job. A driver
that starts a sandbox on that host mounts the directory into it and names the
mount as `DEVCLOUD_MIRROR_DIR`; the sandbox's `devenv up` then clones with
`--reference` to it, so a checkout takes seconds. A sandbox lives hours; its
clone reads objects from the mount for that long.

Steps 2–4 reach only the public internet (Google's APIs, Tailscale's control
plane); nothing reaches the tailnet's services before the profile names them.

**The profile** is `~/.claude/devcloud/` in the configuration repository.
Only `managed-settings.json` is required.

- `managed-settings.json` — written to `/etc/claude-code/managed-settings.json`,
  which every session reads however it started; it holds only what a host
  must change (the synced `settings.json` supplies the rest, merged key by
  key), and its `env.ANTHROPIC_BASE_URL` is the gateway step 6 checks. Boot
  adds `"prependPlugins": []` unless the file sets `prependPlugins` or is
  empty: managed settings with any key otherwise seat the engine's security
  default, which passes the plugins a person installs (this guard among them)
  over on classic hooks, the prompt's parts, compactions, and the rows the
  transcript keeps from attachments, hook context and compactions.
- `profile.env` — `KEY=value` lines for `/etc/devcloud/env` (blank lines and
  `#` comments skipped; `$NAME` and `${NAME}` expand from earlier lines, then
  the user's login environment — `HOME`, `USER`, `PATH` — and the host's
  identity, so `PATH="$HOME/bin:$PATH"` resolves once for every reader).
  The profile is every host's, so it never sets a per-host identity:
  `SESSION_MIRROR_HOST`, `DAEMON_HOST` and `DAEMON_BOOT_ID` from `profile.env`
  or a `secrets.toml` env target are dropped, and step 10's detail names them.
- `secrets.toml` — what to fetch from Secret Manager and where to put it:

      [[secret]]
      name = "<Secret Manager secret id>"   # required; the latest version is read
      store = "KEY"        # also written to the secret store as KEY (the guard reads it)
      env = "VAR"          # exported through /etc/devcloud/env
      file = "~/path"      # the value, or the template, written here (inside the home)
      template = "..."     # {value} substituted; without it the file is the value
      mode = "0600"        # default 0600; parent directories created 0700
      optional = true      # absent in Secret Manager -> "missing", the boot goes on

  A store entry and a template-less file get the payload byte for byte; a
  template or an env target gets it with one trailing newline dropped. Every
  file is written as the user, through a new file renamed over the target. An
  env value must fit on one line. Every entry is tried before a required one
  that failed fails the step.
- `home/` — files copied, nested paths kept, into the user's home at boot and
  at every reconcile: the git identity, `.tmux.conf`, a host-safe `.zshrc`.
  Never a secret: those arrive only through `secrets.toml`.
- `build.env` — `DEVCLOUD_USER`, `DEVCLOUD_UID`, `DEVCLOUD_HOME`, read where
  the image is built.

**The environment** reaches every process by who reads it: Claude Code
settings through managed settings; credentials as files; everything else in
`/etc/devcloud/env` (mode 0640, the user's group), which every zsh of the
user's reads through `/etc/zsh/zshenv` (login, interactive, and the `zsh -c`
of Claude Code's Bash tool), bash login shells through
`/etc/profile.d/devcloud.sh`, and services as their environment file. Every
value is written double-quoted with `\`, `"`, `$` and the backtick escaped,
which shells and systemd read alike. Root's shells skip it: it can put the
user's directories on `PATH`. Under the profile's pairs it holds the image's
own defaults (`steps.IMAGE_ENV`): `WEB_CHROME`, the headless Chromium the
`web` plugin renders with, so that a session a service starts finds it too;
`WEB_CHROME=none` in `profile.env` turns rendering off.

**Rendering and the Chromium sandbox.** The fetch tool launches Chromium
with its sandbox, which needs unprivileged user namespaces. Ubuntu 24.04
grants them a program only through an AppArmor profile naming it; the image
carries one for its headless shell
(`/etc/apparmor.d/devcloud-chrome-headless-shell`, like Ubuntu's own for
Google Chrome), which a VM loads. In a container the runtime decides:
Docker's default seccomp profile refuses them, so a container started as
above keeps the plain fetch with a note that rendering failed (`No usable
sandbox!`), and one started with `--security-opt seccomp=unconfined` renders.

**Configuration is received, never sent.** `~/.claude` is a clone whose push
URL is invalid, so a push fails loudly. The config pull job fetches and resets
it to the branch every 30 minutes — an edit made on a host lasts until then —
and, when the commit moved, runs `devcloud reconcile` (steps 5–11), so a
profile change made on a Mac reaches managed settings, the environment and
the services without a reboot. Untracked files are left alone.

**The services:**

| service | runs | as |
|---|---|---|
| `pull-config` | `devcloud pull-config`, every 30 min | root |
| `refresh-secrets` | `devcloud refresh-secrets` (steps 7, 10, 11), every 30 min | root |
| `refresh-mirrors` | `devcloud refresh-mirrors`: fetches the mirror cache, every 30 min; nothing on a sandbox | root (git as the user) |
| `session-mirror` | `~/.claude/tools/session-mirror ship`, continuously, when the configuration has it | the user |
| `sminos-daemon` | `sminos daemon run`, on a persistent host that is a sminos machine only | the user (a systemd user unit) |
| `lease` | `devcloud lease tick`, every 5 min on persistent hosts: lease warning and departure, tailnet rejoin retries, and the VM idle notice | root |

Under systemd they are units `devcloud-<service>` (the jobs as timers), except
the sminos daemon, which is the user's own unit `sminos-daemon.service` in
`~/.config/systemd/user/` (the default directory, which the user manager reads
whatever the profile sets `XDG_CONFIG_HOME` to). Each unit runs its command
through `devcloud run-scrubbed --`, which passes the command's output to
journald scrubbed of every value the host holds. The shipper runs only on a
host a boot made: the boot writes `/run/devcloud/booted` when it exits 0 or 3
and removes it when it starts, and the unit is ordered after the boot and
conditioned on that file, so after a boot that failed it stays down. During a
boot, step 11 leaves the shipper's start (or owed restart) to the boot's end,
which queues it once the marker is written — so a boot run by hand, with no
unit job for the start to wait behind, still ends with the shipper running. A
restart or reload a run owes is recorded under `/var/lib/devcloud/pending/`
before the first systemctl call and cleared once made, so a run that fails
leaves it for the next.
Elsewhere `devcloud-services` runs them as the container's PID 1: it runs
the services `/run/devcloud/services.json` names — step 11 rewrites it at
every boot and reconcile, so a service whose program a pull brings starts
and one whose program a pull removes stops — reaps orphans, restarts a
crashed service after 1, 2, 4 … 60 s, restarts a continuous service when
`/etc/devcloud/env` changes, and forwards what a service prints to its own
output as `<service>: <line>`, scrubbed as a stream before it is split into
lines or cut to 4 KiB, of every value the host holds, or held while the
supervisor ran (it rereads them whenever their files change, before it
forwards another byte). A service it stops for a reconcile — removed, or
restarted for a new environment — gets SIGTERM and, 8 s later, SIGKILL. On
its own SIGTERM it forwards the signal to every child and waits up to 8 s
(the shipper's final pass) before it exits.

**The idle notice.** A VM, kept or leased, sends a notice after three days
without activity, and every three days of that idle stretch thereafter.
Activity means a transcript under the user's `~/.claude/projects` changed
since the previous check, a `loginctl` session has a terminal, or the
15-minute load average is at least 0.5. A resident session waiting for a
message and noninteractive SSH probes do not count. The first check starts
the clock; `/var/lib/devcloud/idle.json` keeps the last check, last activity
and last notice times across reboots. Adopted machines are excluded.

The notice starts `devcloud on <name>:` to identify its automated origin,
since sminos labels a host-shell message as `from human`. It names the VM,
its idle time and last activity, its lease end (or
that it runs until `down`), its estimated cost at the creation-time list
price when known, and every checkout with unpushed work. It gives
`devcloud vm down <name>` to end it; **idleness never stops or deletes a VM**.
Delivery tries the creating session, then its sminos project's live
sessions. If none are live, it leaves an untagged note in that project's
log for the next session. Without a usable route it goes to the journal
and `wall`. The lease warning uses the same fallback. `devcloud vm ls`
reads the host's idle clock over the tailnet; an unavailable clock shows `-`.

**sminos.** Step 11 first links `/usr/local/bin/sminos` to the launcher in
the doperpowers marketplace clone, at every boot and reconcile, so any shell
on the host finds it (the profile's `sminos` is an interactive zsh alias,
which a command over SSH never loads). A persistent host is a sminos machine once the person enrolls it
(`sminos hub enroll`, a human step: its code carries the organization's key),
which leaves `$SMINOS_HOME/daemon/hub.json`. On the host, as the image's user
in that user's own login shell:

    su - <user>
    sminos hub enroll        # paste the code at the hidden prompt
    sminos hub show          # the machine's enrolled identity

A login shell, because the command's paths must expand in the user's
environment: typed from root as `runuser -u <user> -- ~/.claude/...`, root's
shell expands `~` to `/root` before the switch, and the enroll fails with
permission denied. From then on step 11 — at the
next boot, or at once with `devcloud reconcile` — runs `sminos daemon
install` as the user (the doperpowers marketplace clone's `sminos.py`, which
`sync/apply.py` installs), adds a drop-in naming `/etc/devcloud/env` as the
unit's environment file, turns lingering on, reloads the user manager, and
enables and starts `sminos-daemon.service`, restarting it when its unit or
the environment changed (an owed restart is kept in
`/var/lib/devcloud/sminos-restart-pending` until one succeeds, so a failed
attempt's retry still makes it); lingering starts it again after a reboot.
A host is a sminos machine as well once it is cut over to its MAWS endpoint
(`daemon/identity.json`, which the endpoint's first complete welcome writes;
its sminos then speaks only to the endpoint and holds no `hub.json` at all
when the host was born under the v2 code), and before that, from its first
boot, when its descriptor names MAWS's code: step 11 starts the daemon so
that step 13's listing cuts it over within seconds. A cut-over host enrolls
nothing at step 11 (its enrollment is its endpoint's). Otherwise nothing is
installed and the host's projects run local-only.
A sandbox is never a sminos machine: one whose `$SMINOS_HOME/daemon/` holds
`hub.json`, `machine.json` or `identity.json` (an enrollment, the instance
claim a daemon writes, a cutover) fails step 11 — it shares the identity of the machine it was copied
from — and is left as it is, since the directory may be that machine's own,
mounted. A container's `DAEMON_BOOT_ID` is its own (step 1), never its host's.

**MAWS's endpoint.** A VM created with the MAWS project (`--project maws`, or
`<owner>/MAWS`) under a driver profile that names MAWS's v2 provisioning code
(`[desk] provisioning_secret_v2` and `delegation_id`) carries both in its
descriptor. Step 1 puts the delegation's id in `/etc/devcloud/env` as
`MAWS_DELEGATION_ID`, so step 12's `devenv up maws` installs `mawsd` with its
machine ref minted under the delegation (`<id>_…`). Step 13 fetches the code
and pipes it, on stdin only, to `mawsd endpoint provision --name
<DEVCLOUD_NAME> --wait 120` as the user, which redeems it into a certificate
under the delegation and is `org-listed` with no hand in it; sminos's daemon,
already running, is cut over at the endpoint's first welcome. An endpoint the
hub confirmed whose certificate is not yet live (exit 4), or a `mawsd` that
does not answer yet, defers the step: the `devcloud-enroll` service runs the
same command every 5 minutes until it is listed, and the provisioning resumes
without redeeming again. A refusal fails the step with its reason. `devcloud
reconcile` runs the step again; the periodic jobs do not. At its departure
(and an adopted machine's release) such a host retires its certificate
itself — `mawsd endpoint retire` signs the retirement with the delegation's
key, posts it, frees the hub row so a recreated VM may take the name, and
destroys the keys — before its logout, and `mawsd.service` stops with
devcloud's services. When it cannot (or the endpoint holds a member's
attended enrollment, whose key only an admin retires), the departure goes on
and names, at that run and every rerun until a retirement succeeds
(`/var/lib/devcloud/desk-residue`, written before a retirement starts and
removed only once one is confirmed), the command the owner runs from a MAWS
worktree on a Mac: `zsh
apps/desk-hub/deploy/production-run.sh admin machine drop <name>`, which the
driver also names after a delete whose departure was not confirmed. A VM
created without the MAWS project boots as before.

**Status.** `devcloud status` prints `/var/lib/devcloud/status.json` one line
per step — name, state (`ok`, `failed`, `skipped`, `missing`), when, detail —
and exits 1 unless the last boot finished with no failed step. A reconcile or
a job records its steps the same way. A detail names steps, keys, secret ids,
exit codes and log paths, never a value. A command's output goes to a
root-only log under `/var/log/devcloud/`, cut to its last 200 lines and with
every value devcloud knows scrubbed to `[secret]` first — the bootstrap
token, access tokens, the seed key's private fields, every secret it read,
and what the host already holds (the store, the env targets, the file
targets), in each spelling a command prints by accident. Permissions are not
what keeps a value out of a log.

    devcloud status            # one line per boot step
    devcloud reconcile         # steps 5-11 against the configuration as fetched now
    devcloud pull-config       # the pull job, by hand
    devcloud refresh-secrets   # the refresh job, by hand
    devcloud refresh-mirrors   # the mirror job, by hand

## The VM driver (`driver/`, `bin/devcloud`)

`devcloud vm` creates cloud machines that boot into hosts, lists them, reaches
them, leases them and deletes them, from a session on the person's Macs
(design: `docs/doperpowers/specs/2026-10-21-devcloud-vm-driver-design.md`).
The plugin's `bin/devcloud` is on a session's `PATH`; it runs
`boot/devcloud` with a Python 3.11+ from `PATH`, which hands `vm` to the
driver with the caller's `PATH` (hcloud and gcloud live under Homebrew and
the user's SDK). On a host (`/etc/devcloud/boot.env` exists) `devcloud vm`
refuses with exit 6: hosts never drive. A session learns it from
`skills/vm/SKILL.md` (`devcloud:vm`).

    devcloud vm up [--label L] [--project owner/repo[@ref]]... [--account A] [--type T] [--location L]
                   [--disk GB] [--ttl D | --keep] [--spot] [--enroll-code -] [--confirmed] [--dry-run]
    devcloud vm adopt <user@address> [--label L] [--project …]... [--ttl D] [--confirmed] [--dry-run]
    devcloud vm ls [--json]
    devcloud vm ssh <name> [--root] [-- command...]
    devcloud vm lease <name> <duration|keep>
    devcloud vm down <name> [--force]
    devcloud vm reap [--install]
    devcloud vm provider register <account> --confirmed | provider test <account>

Exit codes: 0 ok, 1 failed, 2 usage, 3 the provider refused (or a capability
the request needs is missing), 4 over a cap (needs `--confirmed`), 5 the down
guard (unpushed work), 6 not a driver here (no seed key, or a devcloud host),
7 the account's provider is not usable (not registered, or no passing copy).

**What it needs.** The profile's `driver.toml` (beside the host profile in
`~/.claude/devcloud/`, or `$DEVCLOUD_PROFILE`): the caps, the default
account, the descriptor fields every host gets (`[host]`), the desk
(`[desk]`: the v1 `provisioning_secret` that enrolls sminos on DX2, or MAWS's
`provisioning_secret_v2` with its `delegation_id`, never both, and the
`name_prefix` VM names are drawn under, `dc-` by default, the delegation's
own), and the accounts, each a provider with the
Secret Manager ids of its credentials (`env`) and its settings (`vars`);
never a value, and unknown keys are refused. The seed key file,
`$DEVCLOUD_SEED_FILE` or `~/.config/devcloud/seed.json`: the driver signs
its own token request with it (RS256 in the standard library; no gcloud
configuration is touched) and reads each credential from Secret Manager on
every provider call. Without a seed every command exits 6.

**Caps.** A VM is kept (no lease; it runs until `down`) unless `--ttl`
gives it one, or the profile's `[caps] lease_default` names a duration. A
session may create one, kept or leased, within the profile's caps without
asking anyone: at most three unconfirmed VMs alive across accounts
(`unconfirmed`), at most 8 vCPU, and no disk added beyond the type's own
above 200 GB. A lease's length is not capped. Anything beyond, and
registering a provider, need the person's yes for that request, passed as
`--confirmed`; a VM so made carries `devcloud-confirmed=1` and is not
counted. A profile that still names the old keys `throwaway` or `lease_max`
is refused, naming what replaced them.

**`up`** checks the caps (`--dry-run` stops there, printing the request,
each cap's verdict and the hourly price), names the VM `<prefix><label>-<4 hex>`
(no live server, tailnet node or desk machine of that name), composes the
boot descriptor (ids, never values) and user-data that stages it at
`/var/lib/devcloud-stage/boot.env` and authorizes every driver key for root,
and creates the server with its labels in the create call itself, from the
account's newest image whose recipe hash (`image/` and `boot/`, hashed) is
current, else from the provider's Ubuntu. It counts again (two drivers
racing past the cap: the newest goes), then, at the public address, on the
slow path streams the plugin's `image/` and `boot/` and runs `setup.sh`,
delivers the seed (its path in the host's credential ledger
first, the key on ssh's stdin), installs `/etc/devcloud/boot.env` and starts
the boot, and waits for every step, over the tailnet once the tailnet attach
step is `ok` (the boot closes the public port right after it). Where the
provider attaches the seed itself (`metadata_seed`, GCE), nothing is done
over SSH before the tailnet: the user-data also carries, on the slow path,
the recipe as a gzipped tarball and a first-boot script that runs
`setup.sh`, then ledgers and installs the descriptor and starts the boot
(`/var/log/devcloud-first-boot.log` on the VM). A failed step
prints `devcloud status` and exits 1, keeping the VM for inspection.
`--enroll-code -` reads a one-time desk code from stdin and, after the boot,
writes it to the host and reconciles, for when the profile has no
provisioning key; it is refused for a VM that provisions MAWS's endpoint,
whose name a DX2 row would hold. With `--project`, the first project's `devenv/host.toml`
(`account`, `type`, `location`, `disk_gb`, `spot`; read from the session's
checkout when it is that repository, else from GitHub with `gh api`) sits
between the flags and the profile's defaults; an unknown key or an account
the profile lacks is exit 2 before anything runs.

**Images.** `image build [--account A]` creates a builder (the smallest type
with the provider's least disk, labeled `devcloud=builder`, given the driver
keys and nothing else), runs `setup.sh`, checks that it holds no descriptor,
seed, credential file the guard knows or sminos enrollment
(`driver/bake_check.py`), resets cloud-init, the machine id, the SSH host
keys and the tailnet state, powers it off and records the image
(`devcloud=image`, the recipe hash), then deletes the builder. A bake that
fails labels its builder `devcloud-bake=failed-<step>` and deletes it.
`image ls` lists them. The scheduled reaper builds an image for an account
that lacks a current one, at most once a day per account and never while a
builder of the account is alive.

**`ssh`** reaches the host's user over the tailnet (`--root` for root); one
argument after `--` is a shell line as given, several are an argument list,
each quoted. A host whose departure has started is refused except to root.
**`lease`** writes the host's lease first (`devcloud lease set`, under its
lock), then the provider label with the value the host printed; `lease
<name> keep` removes the lease, and leaves `devcloud-confirmed` as `up` set
it, so the VM stays counted. A change between kept and leased makes the
host's tailnet node rejoin as the other kind, ephemeral while leased, under
the same name (`devcloud-rejoin`; a non-ephemeral node is removed through the
Tailscale API, so the OAuth client needs the `devices:core` scope), and
`lease` waits for it to come back. **`down`**
refuses unpushed or uncommitted work under the user's `~/Developer/GitHub`
(exit 5; `--force` proceeds), departs the host (`devcloud depart --force
--no-poweroff`, `--no-hold` with `--force`) and deletes it after rechecking
its labels; the connection dropping after `devcloud-depart: ready-to-logout`
is success, before it the outcome is unknown and the VM is kept.
A host that leaves for good removes its own tailnet node through the
Tailscale API right after its logout, unless the node is ephemeral (a
logout removes those), and the release of an adopted machine does the
same. After every VM delete, the reaper's too, and after an adopted
machine's verified release, the driver removes what the API still lists
of that host. A node counts as the host's only when it is tagged
`tag:devcloud` and reports exactly the host's name as its hostname. Each
node is removed by its id, and the deletion's line names that id.

**The reaper**, `devcloud vm reap`, deletes what outlived its lease (a
reachable host departs first; a label older than the host's lease is
repaired, not acted on; a running host that does not answer gets 6 hours; a
held departure 24 hours, logged as unshipped loss), unconfirmed VMs above
the cap made in the last 2 hours (newest first; an older one over the cap,
which a lowered cap can leave, is named, never deleted, since it may hold
days of work), builders and `provider test` servers older
than 2 hours, and images beyond the newest two. It never touches a resource
without the `devcloud` label. Every delete and relabel, the reaper's and
every command's, reads its target again first: a server with a `get` (its
`devcloud` label, and for the reaper the lease and state it decided on), an
image with a fresh `images` (still listed, with the labels it was chosen by).
Each deletion is a line in `~/.local/state/devcloud/reap.log`. `up` and `ls`
run it bounded first: no departures, 60 seconds in all, its lines on stderr;
`reap --install` writes a launchd agent that runs it every 10 minutes, on the
always-on Mac; the agent runs the marketplace clone's `bin/devcloud` when
there is one, else the copy that installed it, and each of its runs ends
with one dated line in `~/.local/state/devcloud/reap.out`. `up` counts the unconfirmed VMs only from lists that answered:
an account whose list fails stops the `up` before anything is created.

**Providers** are executables speaking one JSON request on stdin and one JSON
answer on stdout per operation (`info`, `types`, `create`, `list`, `get`,
`set-labels`, `delete`, and with images `image-create`, `images`,
`image-delete`); exit 3 is a refusal (`{"error", "kind"}`), any other
non-zero exit a failure. The driver gives a provider its account's
credentials in its environment only and scrubs them from its stderr.
`driver/providers/hetzner` ships here (it drives `hcloud` under a private,
empty configuration), and so does `driver/providers/gce`: it drives `gcloud`
under its own `CLOUDSDK_CONFIG` (`~/.local/state/devcloud/gce/gcloud`) with
the driver's seed activated there, so the Mac's own gcloud identity is never
read or changed. Its account's `vars` name the project (`GCE_PROJECT`), the
host service account every instance runs as with the `cloud-platform` scope
(`GCE_SERVICE_ACCOUNT`, the host's seed through the metadata server, so no
key file reaches the VM), the image family (`GCE_IMAGE_FAMILY`), the boot
disk (`GCE_DISK_GB`, 50 by default) and any custom machine types to offer
(`GCE_CUSTOM_TYPES`, since a zone lists none). It offers the zone's x86-64
types with at least 2 dedicated vCPUs and 2 GB and no accelerator, priced
from the Cloud Billing catalog (cached a week), creates every instance with
`block-project-ssh-keys=TRUE`, a spot request with termination action
`DELETE`, and images in the family from a stopped builder's boot disk. A provider of the person's own lives in the profile's
`providers/<name>`: the person registers it once (`provider register
<account> --confirmed` records its sha256 in `driver.toml`), and `provider
test <account>` runs it through the conformance sequence on a real server; a
pass copies the exact bytes tested to `providers/.pass/<account>` with a
record of their sha256, and every call runs that copy, its sha256 checked
before each call, so an edit is in use only once it has passed.

**`adopt`** makes an Ubuntu 24.04 machine the driver did not make a host,
always with `--confirmed`, its target from the command line only. Lifetime
is `keep` unless `--ttl`. It first reaches `<user>@<address>` with the
person's own SSH key (sudo for a user other than root), refuses another OS
and a machine that already holds a descriptor its own record does not
match, then saves root's and the login user's `authorized_keys` to
`/var/lib/devcloud-adopt/` (once), authorizes the driver keys for root,
streams the recipe and runs `setup.sh`, stages a descriptor with
`DEVCLOUD_ADOPTED=1`, delivers the seed and starts the boot, as the slow
path of `up` does. Its record, `~/.local/state/devcloud/adopted/<name>.json`,
holds the address, the login user, the lease and the phase, written before
the step it names (`preparing`, `seeded`, `booted`, `released`); `adopt` run
again for the same target resumes from it. `ls` lists adopted machines
(an unfinished adoption with its phase), never counted against the cap, and
the reaper never touches them. `lease` writes the host's lease and the
record; there are no labels. `down` (and the host's own lease end) runs
`devcloud release`: the machine leaves the desk and the tailnet, devcloud's
firewall, units and every credential its ledger lists go, the saved keys
come back, then devcloud's state directory (`/var/lib/devcloud`), and the
machine keeps running; the user and the rest of the home stay. Adopting a
released machine again is not supported: what the home keeps (the
configuration checkout, among others) still fails `setup.sh`'s final check. `down` releases over the tailnet, else as root at
the recorded address, else (a release that stopped after it gave the keys
back) as the original login user there with the person's own key, and
removes the record only once a new connection as that user finds nothing of
devcloud left. Like `up`, `adopt` refuses while this Mac's driver key is not
yet in the configuration repository.

**Local state** is `~/.local/state/devcloud/`: the driver Mac's SSH key (its
public half written to the profile's `driver-keys/<machine>.pub`, which the
configuration sync pushes and every host authorizes), a `known_hosts` keyed
by the server rather than its address (an adopted machine by its name), the
reap log, when the reaper last tried each account's image build
(`image-builds.json`), the adoption records (`adopted/`) and the gce
provider's private gcloud configuration and price cache (`gce/`).

## Developing

    devcloud/tests/run.sh                                      # the host: unit tests, the image, containers
    devcloud/tests/mods/run.sh                                 # the mod's tests
    claude plugin validate devcloud/.claude-plugin/plugin.json
    tests/mods/typecheck.sh                                    # every plugin's mods, typechecked
    claude --plugin-dir devcloud                               # the working tree as the plugin

Typechecking reads the declarations the engine lays in
`devcloud/.claude-plugin/types/` as a session loads the plugin, as
doperpowers' own mods do (`hooks/mods/README.md`). The host's integration tests
(`tests/integration.py`) build the image and boot it in containers against
stand-ins (`tests/fixtures/fakes.py`) for Secret Manager, the metadata
server, the configuration repository, GitHub's project repositories (a
`url.insteadOf` rule in the stand-in profile's `.gitconfig`) and the gateway,
with a stand-in `devenv` runner (the person's own is private), which clones
this checkout as a project and runs its `devenv/`; three environment
variables point a host at such stand-ins and exist for that use:
`DEVCLOUD_SM_ENDPOINT` (Secret Manager's base URL), `GCE_METADATA_HOST` (the
variable Google's libraries read) and `DEVCLOUD_ALLOW_HTTP=1` (a plain-HTTP
configuration repository); `DEVCLOUD_JOB_INTERVAL` shortens the jobs' period
under `devcloud-services`. The ci-kit gates `devcloud-unit`, `devcloud-image`,
`devcloud-host` and `devcloud-systemd` run `tests/run.sh` one part each
(`DEVCLOUD_PART`; unset, it runs everything) on GitHub's hosted runners,
which have Docker; each integration part builds the image itself. Versions: `scripts/bump-version.sh --plugin
devcloud <version>` moves devcloud's `plugin.json` and its marketplace entry,
never doperpowers'.
