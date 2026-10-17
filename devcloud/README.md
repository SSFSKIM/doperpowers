# devcloud

A second plugin in the doperpowers marketplace, installed on its own
(`claude plugin install devcloud@doperpowers`): doperpowers stays the
workflow plugin, and a person opts into devcloud. It carries the secrets
guard, and the host image and boot program that make any Linux userland
work like the person's Mac; the `devenv` skill follows (design:
`docs/doperpowers/specs/2026-10-15-devcloud-design.md`).

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
system-prompt section listing the stored keys — stays in `cua`. When a
session starts, devcloud sets its guard marker in `$.state`
(`{ plugin: 'devcloud', key: 'secrets-guard' }` → `{ owner: 'devcloud',
version: 1 }`, typed in `types/devcloud.d.ts`): every plugin in the session
reads it, only devcloud writes it, and a `claude` a tool call starts has a
session of its own. `cua`'s scrubbing stands down while it is set, so one
guard decides every handle. (A `globalThis` symbol does not work: the engine
evaluates each plugin's module in a realm of its own.)

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
Tailscale, the Docker client, zsh, and Claude Code (native installer, as the
user) — and creates the user from three build inputs, `DEVCLOUD_USER`,
`DEVCLOUD_UID` and `DEVCLOUD_HOME`, the Mac's own account, so a session
moves between a Mac and a host under the same paths. It carries no
credential, no descriptor, no `~/.claude` checkout and no sminos enrollment.
`image/Dockerfile` runs `setup.sh` as its one step; a VM builder runs it and
snapshots, and its `devcloud-boot.service` runs the boot at every start.

    docker build -t devcloud -f devcloud/image/Dockerfile \
      --build-arg DEVCLOUD_USER=<user> --build-arg DEVCLOUD_UID=<uid> --build-arg DEVCLOUD_HOME=<home> .
    docker run -d --name <name> --hostname <name> \
      -v "$DESC":/etc/devcloud/boot.env:ro -v "$SEED":/run/devcloud/seed.json:ro devcloud

A container cannot set its own host name, so the driver passes
`--hostname` and the boot only checks it. Its entrypoint is
`devcloud-boot && exec devcloud-services`: a failed boot ends the container,
and `docker run --restart on-failure` retries it from the top.

**The boot descriptor**, `/etc/devcloud/boot.env`, the only per-host input
(unknown keys are refused):

    DEVCLOUD_NAME=<host name>                  # unique; sandboxes sbx-<random>; a container's --hostname
    DEVCLOUD_KIND=vm|microvm|container
    DEVCLOUD_ROLE=persistent|sandbox           # persistent requires systemd as PID 1
    DEVCLOUD_TAILSCALE=join|host|none          # a sandbox never joins
    DEVCLOUD_TS_AUTHKEY_FILE=<path>            # join only; deleted after use
    DEVCLOUD_SEED=file:<path>|gce-metadata
    DEVCLOUD_SM_PROJECT=<GCP project id>
    DEVCLOUD_CONFIG_REPO=<https clone URL>
    DEVCLOUD_CONFIG_BRANCH=<branch>            # default main
    DEVCLOUD_CONFIG_TOKEN_SECRET=<Secret Manager id of the GitHub token>
    DEVCLOUD_PROJECTS="<entry> ..."            # optional; <name>[@ref] | <owner>/<repo>[@ref]
    DEVCLOUD_MIRROR_DIR=<path>                 # optional

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
| 1 | `identity` | refuses `persistent` without systemd as PID 1; sets the host name (VM) or checks it (container); writes `SESSION_MIRROR_HOST`, and for a container a `DAEMON_BOOT_ID` of its own, fresh at each container start |
| 2 | `tailnet-attach` | `join`: `tailscale up` with the auth key file, then deletes it |
| 3 | `seed` | activates the seed and takes an access token |
| 4 | `bootstrap-secret` | reads the GitHub token `DEVCLOUD_CONFIG_TOKEN_SECRET` names |
| 5 | `configuration` | as the user, clones or fetches and resets `~/.claude`; the token reaches git through a credential helper reading a root-owned file the user's group can read, deleted after the fetch — never a URL or `.git/config`; then reads the profile |
| 6 | `tailnet-check` | the gateway named in the profile's managed settings answers |
| 7 | `secrets` | materializes `secrets.toml` |
| 8 | `home` | as the user: copies the profile's `home/`; the seed as gcloud's account and ADC, the Secret Manager project as gcloud's default; `gh auth setup-git` when gh has a `hosts.yml` |
| 9 | `apply` | runs the configuration's `sync/apply.py` as the user |
| 10 | `settings-and-env` | writes `/etc/claude-code/managed-settings.json` and `/etc/devcloud/env`; `TZ` sets the system time zone |
| 11 | `services` | installs or starts the services; restarts one whose unit or environment changed |
| 12 | `projects` | `skipped` in this version (project environments arrive with `devenv`) |

**The profile** is `~/.claude/devcloud/` in the configuration repository.
Only `managed-settings.json` is required.

- `managed-settings.json` — copied to `/etc/claude-code/managed-settings.json`,
  which every session reads however it started; it holds only what a host
  must change (the synced `settings.json` supplies the rest, merged key by
  key), and its `env.ANTHROPIC_BASE_URL` is the gateway step 6 checks.
- `profile.env` — `KEY=value` lines for `/etc/devcloud/env` (blank lines and
  `#` comments skipped; `$NAME` and `${NAME}` expand from earlier lines, then
  the user's login environment — `HOME`, `USER`, `PATH` — and the host's
  identity, so `PATH="$HOME/bin:$PATH"` resolves once for every reader).
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
user's directories on `PATH`.

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
| `session-mirror` | `~/.claude/tools/session-mirror ship`, continuously, when the configuration has it | the user |

Under systemd they are units `devcloud-<service>` (the jobs as timers).
Elsewhere `devcloud-services` runs them as the container's PID 1: it reaps
orphans, restarts a crashed service after 1, 2, 4 … 60 s, restarts a
continuous service when `/etc/devcloud/env` changes, and on SIGTERM forwards
the signal to every child and waits up to 8 s (the shipper's final pass)
before it exits.

**Status.** `devcloud status` prints `/var/lib/devcloud/status.json` one line
per step — name, state (`ok`, `failed`, `skipped`, `missing`), when, detail —
and exits 1 unless the last boot finished with no failed step. A reconcile or
a job records its steps the same way. A detail names steps, keys, secret ids,
exit codes and log paths, never a value; commands' output goes to root-only
logs under `/var/log/devcloud/`.

    devcloud status            # one line per boot step
    devcloud reconcile         # steps 5-11 against the configuration as fetched now
    devcloud pull-config       # the pull job, by hand
    devcloud refresh-secrets   # the refresh job, by hand

## Developing

    devcloud/tests/run.sh                                      # the host: unit tests, the image, containers
    devcloud/tests/mods/run.sh                                 # the mod's tests
    claude plugin validate devcloud/.claude-plugin/plugin.json
    npx -p typescript@5 tsc -p devcloud/hooks/mods/tsconfig.json
    claude --plugin-dir devcloud                               # the working tree as the plugin

Typechecking reads `.claude/types/claude-code.d.ts` at the repository root,
as doperpowers' own mods do. The host's integration tests
(`tests/integration.py`) build the image and boot it in containers against
stand-ins (`tests/fixtures/fakes.py`) for Secret Manager, the metadata
server, the configuration repository and the gateway; three environment
variables point a host at such stand-ins and exist for that use:
`DEVCLOUD_SM_ENDPOINT` (Secret Manager's base URL), `GCE_METADATA_HOST` (the
variable Google's libraries read) and `DEVCLOUD_ALLOW_HTTP=1` (a plain-HTTP
configuration repository); `DEVCLOUD_JOB_INTERVAL` shortens the jobs' period
under `devcloud-services`. The ci-kit gate `devcloud` runs `tests/run.sh` on
GitHub's hosted runner, which has Docker. Versions: `scripts/bump-version.sh --plugin
devcloud <version>` moves devcloud's `plugin.json` and its marketplace entry,
never doperpowers'.
