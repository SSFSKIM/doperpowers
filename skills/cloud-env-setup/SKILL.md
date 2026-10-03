---
name: cloud-env-setup
description: Use when asked to set up the environment for this project, write the environment manifest, a cloud env, environment.json, or an install script for this repo — making a repository ready for devenv on your human partner's machines (the laptop, the mini, the devbox), or refreshing a project's .devbox/ when its setup changed.
---

# Setting up a project's environment

A project is ready when `devenv up <name>` installs it from nothing, `devenv start <name>` brings
its services up, `devenv validate <name>` checks it, and a session opened in it finds a `devenv`
skill saying how to run and check it — on every host, from files committed under `.devbox/`. The
hosts are persistent machines, not snapshots: the install runs again on every refresh, so it must
be idempotent, and the same files serve the laptop, the mini and the devbox because every host
has the same paths.

Everything you write is a decision someone else's session will execute without you. A manifest
field that guesses, or an install line that never ran, fails on the first host that trusts it.

## The work

1. **Read the repository for how it is really built and run.** CI config is the most reliable
   install recipe; lockfiles and toolchain pins (`packageManager`, `.nvmrc`, `.tool-versions`,
   `Package.swift`) say which tools; `.env.example`, CI `secrets.*` references and the code's own
   environment reads say which variables and secrets exist; `README`/`AGENTS.md`/`CLAUDE.md` say
   how a person runs it. Read a `.env` for its variable names only, with this skill's
   `scripts/env-names [file]` — a value you print lands in the transcript, and `cut -d= -f1`
   prints the body of a quoted multiline key whole.
2. **Check what already works before asking for anything**: `~/.claude/tools/secret-env list`
   for the secret names Secret Manager already holds (names only, never values), `compgen -e` for
   variables already in the environment, `git ls-remote` for repository access.
3. **Draft `.devbox/`** — the manifest, `install.sh`, the start skill (shapes below). When the
   project already has one, its fields are someone's decisions: change what you found wrong, and
   ask before dropping what you merely found unused — a variable nothing in the repository reads
   may be there for your human partner's own tools or checks.
4. **Run the install for real**: `devenv up <name> --force`, read the log under `.devbox/logs/`
   (warnings included), fix, repeat until it passes. Then check the result works — a test run, a
   build — because an install can exit 0 and still leave the project broken (see Known traps).
   Every line of `install.sh` is a command that ran green here; a step you copied from CI or a
   README but did not run is a guess, and it stays out until it has run.
5. **Isolate the app's state before you run it** — the next section. This applies to every run
   of the app, the service you declare and any probe you start by hand while exploring.
6. **Start and validate**: `devenv start <name>`, `devenv status <name>`, `devenv validate <name>`
   until they pass, then `devenv stop <name>`. Leave nothing running that you started. The setup
   describes the project as it is: a check that fails in the project's own code or tests is a
   finding for your report (with its cause, if you found it), not a fix to slip into the setup.
   The check stays in `validate.sh` and fails truthfully; dropping or narrowing it removes the
   project's regression signal, which is your human partner's call.
7. **Commit the `.devbox/` files and the changes the setup needed, by path** — the checkout may
   hold your human partner's own uncommitted work, which stays as it was. devenv gitignores what
   it generates (`env.sh`, `secrets.sh`, `sandbox.settings.json`, `logs/`, `.install-stamp`).
8. **Report**: the commands that passed, with their results; each secret your human partner must
   add, by its Secret Manager name and variable; anything that still fails or that you could not
   check on this host.

## A checkout isolates the code, not the app's state

A development build usually opens the same data your human partner's installed copy uses: the
data or config directory (`~/Library/Application Support/<App>`, `~/.config/<app>`), its
database, sockets, ports, single-instance locks, keychain items, and other tools' config it edits
(`~/.claude/settings.json`, login items). Running it from a scratch clone does not change that,
and neither does a scratch `HOME`: macOS resolves `~/Library` for native and Electron apps from
the account, not from `$HOME`. A dev build of a desktop app, started from a scratch clone while the
installed app was running, migrated the installed app's settings to a newer version it could not
read back and deleted files the running app depended on — and a second, hand-run probe did it
again after the service itself had been fixed.

So before anything runs the app: find where it keeps state (the code's path resolution, not the
README) and the override it honors — an environment variable or flag — and point it at a
directory under `.devbox/` (gitignored) in the service's `cmd` or the manifest's `env`. Use the
same override in every hand-run command. When the app has no override and its state cannot be
separated, declare no service that runs it: validate with a build and tests, and say so in
`start.md` and your report.

## Secrets are named, never valued

A secret enters the manifest as a name — `{"name": "<Secret Manager name>", "env": "<VAR>",
"domains": [...]}` — and its value reaches processes only at launch, through the handler. The
value goes nowhere you write: not the manifest, `install.sh`, `env`, `start.md`, a commit, a log,
or your transcript. This holds when the value is right there in a local `.env` or your human
partner offers it: a value in a file is on one disk, while the manifest has to work on every host,
and Secret Manager is how it gets there.

- Reuse a name `secret-env list` already shows when it is the same credential
  (`devbox-github-pat` is the one GitHub token). Otherwise choose a name (`<project>-<what>`) and
  have your human partner create it — they run
  `gcloud --project ytdownload-505811 secrets create <name> --data-file -` and type the value,
  so it never passes through you.
- `domains` are the hosts the code sends that value to — find them in the code or config (the
  SDK's base URL, the API host), not by guessing from the secret's name.
- Until a declared secret exists, the install warns and runs without it, but `devenv
  claude/shell/start/validate` refuse to launch — they resolve secrets strictly. To check the rest
  meanwhile, run them with `DEVENV_SECRET_ENV` pointing at a stub handler that answers
  `secret-env export <name>:<VAR>` with `export <VAR>=` (empty), and report that the secret's own
  path is unchecked.

## Shapes

`devenv --help` lists the commands. The files:

```
.devbox/environment.json     the manifest
.devbox/install.sh           idempotent, executable; runs from the project root
.devbox/validate.sh          optional: the automated checks `devenv validate` runs
.devbox/skill/SKILL.md       linked into .claude/skills/devenv/ by devenv up
.devbox/skill/start.md       how to run the project
.devbox/skill/validation.md  how to check a change
```

```json
{
  "version": 1,
  "repos": [{"name": "acme-web", "url": "https://github.com/OWNER/acme-web.git"}],
  "install": {"script": ".devbox/install.sh", "timeout_sec": 1800},
  "start_skill": ".devbox/skill",
  "services": [
    {"name": "dev", "cmd": "env ACME_DATA_DIR=\"$DEVENV_ROOT/.devbox/data\" pnpm dev", "cwd": ".",
     "ready": {"http": "http://localhost:3000/"}}
  ],
  "validate": {"script": ".devbox/validate.sh"},
  "network": {"access": "unrestricted", "allowed_domains": []},
  "env": {"NODE_ENV": "development"},
  "secrets": [{"name": "acme-stripe-key", "env": "STRIPE_SECRET_KEY", "domains": ["api.stripe.com"]}]
}
```

- The project's name is its directory under `/Users/new/Developer/GitHub` (`DEVENV_GH`
  overrides it). `repos` holds this repository's HTTPS URL — the hosts have no GitHub SSH key. A
  project spanning several repositories, or one that must be clonable by name on a fresh host,
  also needs a registry entry, `~/.claude/envs/<name>.json` (`name`, `repos` with `ref`, `root`);
  it wins over the repository's manifest field by field.
- `install` runs through `reap` with `env.sh` and the available secrets sourced, logs to
  `.devbox/logs/`, and fails `devenv up` on non-zero. It is skipped while the manifest and script
  are unchanged; list the files whose change should rerun it in a leading comment,
  `# devenv-inputs: package.json pnpm-lock.yaml` (globs from the root) — lockfiles and toolchain
  pins.
- `services` run under `bash -c` in tmux session `<name>`, one window each, with `env.sh` and the
  secrets sourced; `ready` is `{"http": url}` (2xx/3xx) or `{"tcp": "host:port"}`, waited on for
  120 s. Check which address the server really binds: Vite on macOS listens on `[::1]` only, so
  `localhost` answers where `127.0.0.1` does not.
- `validate.sh` exits non-zero on failure; keep it to the checks that need no model calls and no
  human. Without one, `devenv validate` prints `validation.md`.
- `network.access` is `restricted` — with `allowed_domains` naming the package registries and the
  secrets' hosts — only when the install and the tests reach a known, short list of hosts you saw;
  otherwise `unrestricted`. It shapes a sandbox that applies only when a session opts in
  (`devenv claude <name> --sandbox`, or `"sandbox": true`, which you leave unset — that is your
  human partner's call).
- `env` holds non-secret variables only; devenv writes them into `env.sh` and the project's
  `.claude/settings.local.json`, so sessions and seats in the root see them.
- `SKILL.md` carries frontmatter `name: devenv` and description `Use when starting, running, or
  validating this project's development workflow`, and a body that points at `start.md` and
  `validation.md` instead of repeating them.

## Known traps

- **npm 12 blocks dependency install scripts** not covered by `allowScripts`: `npm ci` exits 0
  with an `install-scripts` warning. When a module that needs its script is left broken (the
  check after install fails: better-sqlite3 has no binding), `npm install-scripts approve <pkg>`
  records the allowance in `package.json`; commit it with the setup. A warning for a package that
  works without its script (esbuild ships its binary through optionalDependencies) needs nothing.
  pnpm's equivalent is `allowBuilds` in `pnpm-workspace.yaml`.
- **A platform-bound project** (Swift/Xcode, a macOS-only app) gets an install that checks the
  toolchain and exits 0 with one line saying why it skipped elsewhere, and a `validate.sh` that
  builds only where it can — the devbox runs Linux.
- **Background seats need a trusted workspace**: `sminos spawn --cwd` refuses a fresh clone
  ("Workspace not trusted") until someone runs `claude` there once and accepts. Say so in the
  report when the project will host seats; trusting a directory is your human partner's call.
