# Project environment manifests — living spec

**Date.** 2026-10-02. **Status.** Spec written from the approved design; under independent
review; executing. **Sibling.** `2026-10-02-personal-cloud-env-design.md` (the host layer): this
spec consumes its `secret-env` interface (I1 there) and, for E4, the devbox its M3 produces.
Nothing here changes that spec.

## Purpose

The host layer makes the devbox *the person's computer*. This layer makes each **project** ready
on any of the person's computers the same way: one declaration per project says which
repositories it is made of, how to install it, how to start and check it, what environment and
which secrets it needs. A session that opens on the project finds it installed, its services
startable from one command, and its secrets in the environment without ever having been written
to a file. The same declaration drives the devbox and the two Macs, because every host has the
same paths.

What someone can do after: `devenv up maws` on a fresh devbox clones the project's repositories
under `/Users/new/Developer/GitHub/`, runs the project's install script to completion with a log,
and leaves `.devbox/env.sh`; `devenv claude maws` starts a session in the project root with
`GH_TOKEN` and the project's variables set; `devenv start maws` brings the project's services up
in a tmux session and waits until each one answers; a session working in the project sees a
`devenv` project skill with `start.md` and `validation.md` and knows how to run and check the app;
and the `cloud-env-setup` skill lets an agent author or refresh all of this for a project it has
never seen, by inspecting the repository and running the install for real.

The model is Codex cloud's environment (install_script, start_skill, allowed domains, environment
variables, proxy-substituted secrets) and Cursor's `environment.json` (install, start, terminals),
re-cut for one person's persistent machines: no publication step, no snapshot cache — the home
persists, so install is idempotent and "refresh" is `devenv up` again.

Terms: **manifest** — a project's `environment.json`; **registry** — `~/.claude/envs/`, personal
manifests synced by `claude-config`; **project root** — the directory `devenv` treats as the
working directory (the first repository's checkout, or the registry entry's `root`); **install** —
the idempotent script that makes a checkout buildable; **start skill** — the markdown a session
reads to run and check the project (`start.md`, `validation.md`); **seat** — a background Claude
Code session spawned by sminos (`skills/sminos/`); **secret handler** — `~/.claude/tools/secret-env`
from the host layer; **`claude-config`** — the private git repository that is `~/.claude` on every
host (`~/.claude/sync/sync.sh` commits, rebases and pushes it every 30 minutes).

## Progress

- [ ] E1 — Manifest schema and resolution, `devenv up/claude/shell/show/list`, `env.sh`, `reap`; tests; this repository as the first project
- [ ] E2 — `devenv start/stop/status/validate`, the start-skill link, the shell-rc hook and `settings.local.json` env (seats inherit)
- [ ] E3 — `cloud-env-setup` skill; manifests for doperpowers, MAWS, claude-usage-menubar authored by it
- [ ] E4 — On the devbox: the three projects up, sessions open, secrets through the handler; acceptance run

## Acceptance

Run as written by E4 (E1–E3 prove their own items on the laptop first). `<GH>` is
`/Users/new/Developer/GitHub`.

1. **Resolution.** `devenv show doperpowers` prints the resolved manifest as JSON with `name`,
   `root` (`<GH>/doperpowers`), `repos`, `install`, `env`, `secrets`; `devenv show nosuch` exits 1
   with `no manifest for nosuch; run the cloud-env-setup skill in that repository`.
2. **Up is idempotent.** With `<GH>/doperpowers` moved aside, `devenv up doperpowers` clones it,
   runs `.devbox/install.sh`, writes `<GH>/doperpowers/.devbox/env.sh` and
   `<GH>/doperpowers/.devbox/logs/install-<ts>.log`, and links
   `<GH>/doperpowers/.claude/skills/devenv/{SKILL,start,validation}.md`; a second `devenv up doperpowers` finishes in
   under 15 s and reports `fetched, install skipped (unchanged)`. (E1 proves the install-only
   subset — everything but the link; E2 proves the whole item.)
3. **Environment and secrets.** (i) env.sh carries non-secret env only; `secrets.sh` (I2) holds
   the handler call `…/secret-env export devbox-github-pat:GH_TOKEN` and no value;
   `.devbox/sandbox.settings.json` masks `GH_TOKEN` with `injectHosts` `api.github.com`,
   `github.com`; (ii) `devenv shell doperpowers -c 'echo $NODE_ENV; [ -n "$GH_TOKEN" ] && echo token-set'`
   prints `development` and `token-set`; in a session started by `devenv claude doperpowers` a Bash
   tool command sees `GH_TOKEN` set; (iii) only for a project with `sandbox: true` (or
   `devenv claude --sandbox`): a Bash tool `env | grep ^GH_TOKEN=` shows a `fake_value_` placeholder (mask), not the value;
   `gh api user` succeeds (injection to `api.github.com`); a request to a non-inject host
   (`curl -s -H "Authorization: Bearer $GH_TOKEN" https://httpbin.org/headers`) shows the
   placeholder, not the token; (iv) the handler's value appears nowhere on disk:
   `grep -rlF "<the value>" <GH>/doperpowers/.devbox/` (logs included) finds nothing. On the laptop
   (i), (ii), (iv) and the placeholder halves of (iii) run fake-backed (`DEVENV_SECRET_ENV`); `gh api
   user` and every real-handler run are deferred to "handler present" — the laptop once the
   handler can read Secret Manager there, at the latest E4 (amended 2026-10-02, Decision Log).
4. **Services.** `devenv start maws` creates tmux session `maws` with window `dev` and prints
   `dev: ready (http://127.0.0.1:5173/)` within 120 s; `devenv status maws` lists `dev running`;
   `devenv stop maws` ends the session and `tmux has-session -t maws` fails. This is a macOS check
   (MAWS's `pnpm dev` is electron-vite, which needs a display); on the devbox E4 proves the same
   start/status/stop and readiness with a fixture project whose service is
   `python3 -m http.server 8765` with an `http` ready check.
5. **Validation.** `devenv validate doperpowers` runs `.devbox/validate.sh` and prints
   `validate: pass` (exit 0); in a project with only `validation.md` it prints that checklist and
   exits 0 with `validate: checklist printed (no validate.sh)`.
6. **Reap.** `reap -- bash -c 'sleep 300 & exit 0'` returns within 10 s and `pgrep -f "sleep 300"`
   finds nothing; `reap --timeout 2 -- sleep 300` exits 124 and the sleep is gone.
7. **Seats inherit.** `sminos spawn envtest "print the value of NODE_ENV and stop" --cwd <GH>/doperpowers --wait`
   replies with `development`; a seat spawned with `--settings <GH>/doperpowers/.devbox/sandbox.settings.json`
   that holds `GH_TOKEN` in its environment sees the `fake_value_` placeholder, not the value (a
   sandbox check: run where the sandbox is opted into).
8. **Onboarding by skill.** In `<GH>/claude-usage-menubar` (no manifest yet), the `cloud-env-setup`
   skill produces `.devbox/environment.json`, `.devbox/install.sh`,
   `.devbox/skill/{SKILL,start,validation}.md`, and `devenv up claude-usage-menubar`
   passes on the first run after the skill finishes.
9. **Registry composition.** With `~/.claude/envs/maws.json` naming repos `MAWS` and `doperpowers`
   and overriding `env.NODE_ENV` to `test`, `devenv show maws` prints `root` = `<GH>/MAWS`, both
   repos, and `NODE_ENV: test`; a secret contributed by the non-root repository's manifest appears
   in the resolved `secrets`; `devenv up maws` runs the root's install only, never the non-root
   repository's; the unit tests for merge precedence pass
   (`python3 -m unittest discover -s ~/.claude/tools/tests`).
10. **On the devbox.** `devenv list` names the three projects; `devenv up` for each passes;
    `devenv claude doperpowers -p 'reply with the word pong'` prints `pong`; item 3 holds there
    with the handler's service-account key.

## 1. Where a manifest lives (the human's decision)

Two places, composed:

- **In the repository**, `<repo>/.devbox/environment.json`, versioned with the code it serves
  (Cursor's lesson: environment drift is the standing wound, and a spec beside the code drifts
  least). Its name is the repository's directory name under `<GH>`. A repository-only manifest
  serves an existing checkout; a project is clonable by name only through a registry entry
  (repos with `url` + `ref`). `devenv up <name> --url <https url> [--ref r]` writes that registry
  entry for a single-repository project and proceeds.
- **In the personal registry**, `~/.claude/envs/<name>.json` (synced by `claude-config`): names a
  project that spans several repositories, pins which repositories and refs belong to it, and
  carries personal overrides (an extra variable, a different install timeout, a local port). The
  registry entry wins on collision, field by field; the lists `repos`, `secrets` and `services`
  merge by `name` with the registry's entry replacing the repository's entry of the same name.

Resolution for `devenv <cmd> <name>`: the registry entry if present; else
`<GH>/<name>/.devbox/environment.json`; else exit 1 with
`no manifest for <name>; run the cloud-env-setup skill in that repository`. A registry entry's
repositories are cloned or fetched, and composition is root-only: `install`, `start_skill`,
`services` and `validate` come from the ROOT repository's manifest (or the registry entry); a
non-root repository contributes only its `env` and `secrets` — its install, start skill and
services are ignored. Merge order: non-root repositories in list order, then the root, then the
registry entry; later wins on a key (`env` by variable, `secrets` by `name`). The repository named
by `root` (default: the first) is the project root; env.sh exports `DEVENV_REPO_<NAME>` for every
repository so the root's install script can reach its siblings.

## 2. The manifest

```json
{
  "version": 1,
  "name": "maws",
  "repos": [
    {"name": "MAWS", "url": "https://github.com/SSFSKIM/MAWS.git", "ref": "devbox-manifest"},
    {"name": "doperpowers", "url": "https://github.com/SSFSKIM/doperpowers.git", "ref": "project-env-manifest"}
  ],
  "root": "MAWS",
  "install": {"script": ".devbox/install.sh", "timeout_sec": 1800},
  "start_skill": ".devbox/skill",
  "services": [
    {"name": "dev", "cmd": "pnpm dev", "cwd": ".", "ready": {"http": "http://127.0.0.1:5173/"}}
  ],
  "network": {"access": "unrestricted", "allowed_domains": []},
  "env": {"NODE_ENV": "development"},
  "secrets": [
    {"name": "devbox-github-pat", "env": "GH_TOKEN", "domains": ["api.github.com", "github.com"]}
  ]
}
```

Field semantics, each a decision:
- `repos[]`: cloned to `<GH>/<name>` when absent; `ref` is checked out only on first clone —
  afterwards the checkout is the person's working tree and `devenv up` only `git fetch`es (never
  checks out, resets or pulls: a working tree with the person's changes is never touched). `url`
  is the HTTPS form: the host layer authenticates GitHub through `gh auth setup-git` with the PAT,
  and the devbox has no GitHub SSH key; `devenv up` normalizes a `git@github.com:` URL to HTTPS
  when it meets one.
- `root`: the project root by repository `name`; default the first repository. In a repository's
  own manifest `root` is implied.
- `install.script`: path relative to root; run through `reap` with `timeout_sec` (default 1800)
  and a log at `<root>/.devbox/logs/install-<UTC ts>.log`; must be idempotent (Cursor and Codex
  both make this the contract that makes refresh safe). Exit non-zero fails `devenv up` with the
  log's last 40 lines on stderr. `devenv up` skips install when its fingerprint matches the one
  recorded in `<root>/.devbox/.install-stamp`; `--force` reruns. The fingerprint is sha256 over
  (a) the canonical JSON (sorted keys) of the *effective* composed manifest, (b) the install
  script's bytes, (c) for each `# devenv-inputs: <glob>…` line among the leading comment lines
  after the shebang (globs relative to root), the sorted matched paths each with its content hash
  — a glob matching nothing contributes its own text. The stamp is written only after a
  successful install.
- `start_skill`: a directory relative to root (default `.devbox/skill`) holding `SKILL.md`,
  `start.md` and `validation.md`. `devenv up` links each file into `<root>/.claude/skills/devenv/`
  (I5). `SKILL.md` is what the skill author writes with frontmatter (`name: devenv`, description "Use when starting,
  running, or validating this project's development workflow") and a body that is `start.md`'s
  content pointing at `validation.md`. Claude Code loads it as a project skill.
  `.devbox/skill/` is the documented default source for every repository (it is committed even
  where `.claude/` is gitignored, as in doperpowers); a repository may name another directory.
  The link is a no-op only when source and destination are the same directory.
- `services[]`: optional. `devenv start` opens tmux session `<name>` with one window per service
  running `bash -lc 'source <root>/.devbox/env.sh && exec <cmd>'` in `cwd` (relative to root) — the
  environment comes from env.sh, not the tmux server, which may already exist with another one — then waits up to 120 s for `ready` (`http`: GET
  returning 2xx/3xx; `tcp`: `host:port` accepting) and prints one line per service; `devenv stop`
  kills the session; `devenv status` lists windows and whether each `ready` check passes now.
- `network`: drives Claude Code's native sandbox (the human's decision, 2026-10-02, replacing
  "recorded, not enforced"), opt-in and never blocking. `access` ∈ `unrestricted` (default) |
  `restricted`. `devenv up` writes `<root>/.devbox/sandbox.settings.json` (I9) whenever
  `access` is `restricted` or any secret has `domains`: `sandbox.enabled: true`; when `restricted`,
  `network.allowedDomains` = `allowed_domains` plus every `secrets[].domains` entry, with
  `strictAllowlist: true`; when `unrestricted`, no allowlist. Masking takes effect only from
  user/managed settings or `--settings`, never from a repository's `.claude/settings.json`.
  Applying it is opt-in: `devenv claude` passes `--settings <root>/.devbox/sandbox.settings.json`
  only when the manifest sets `sandbox: true` (optional boolean, default `false`) or the person
  passes `--sandbox`; otherwise the session runs with the host's default settings and the auto
  classifier. A seat opts in by `sminos spawn --settings <that file>` (sminos already takes
  `--settings`; no sminos change). Friction under masking (git push, TLS) is recorded and the
  project's `sandbox` left `false`.
- `env`: non-secret variables, written into `env.sh` literally (shell-quoted).
- `repos[].ref` and existing checkouts: `ref` names the branch carrying the manifest
  (doperpowers: `project-env-manifest`; MAWS and claude-usage-menubar: `devbox-manifest`) until the
  human merges it. For a checkout that already exists, `devenv up` stays fetch-only; E4 has a
  documented preparation step for pre-existing clones: a clean working tree is `git switch <ref>`ed,
  a dirty one stops the run with the tree reported — never reset.
- `secrets[]`: `name` is the Secret Manager name (host layer §5), `env` the variable, `domains`
  the hosts the value may be sent to. In `sandbox.settings.json` each secret with `domains`
  becomes `credentials.envVars` `{name: <env>, mode: "mask", injectHosts: <domains>}` — sandboxed
  commands see a `fake_value_` placeholder, and the proxy substitutes the real value only in
  requests to those hosts — and a secret without `domains` becomes `{name: <env>, mode: "deny"}`;
  `network.tlsTerminate: {}` is set whenever any mask entry exists (experimental in 2.1.283). On
  Darwin the generated settings add `excludedCommands` for `gh`, `gcloud` and `terraform`, which
  can fail TLS under termination. Secrets enter at launch, never inside a session, whether or not
  the sandbox is applied:
  `devenv claude/shell/start/validate` resolve them strictly in the launcher and export them into
  the child's environment, where the sandbox masks them for every Bash tool command; `devenv up`
  resolves them for the install non-strictly (an unavailable secret warns, value-free, and the
  install runs without it, failing on its own if it needed it). No value is ever on disk.
  Known risk, verified in E2 (laptop) and E4 (devbox): `git push`/`fetch` over HTTPS send Basic
  auth, which the proxy's plain-text replacement may not match; if they fail under masking, the
  chosen workaround (`excludedCommands` for `git push*`/`git fetch*`, or an extract rule) goes into
  the generated settings and the Decision Log.
- No `tailscale` field: the auth key is a host-layer concern.

## 3. The tools

All live in `claude-config` (`~/.claude/tools/`, synced to every host): python 3.11, standard
library only (plus calling `secret-env`), one file each, executable, with tests under
`~/.claude/tools/tests/`. `~/.claude/tools` is not on `PATH`: `~/.claude/sync/apply.py` installs
`~/.local/bin/devenv` and `~/.local/bin/reap` as symlinks to them (idempotent), so every host that
syncs has the commands; internal calls use absolute paths.

**`devenv`** — subcommands in Interfaces §I1. `env.sh` (Interfaces §I2) is written to
`<root>/.devbox/env.sh`; it holds no value and so is safe to commit, but it is a per-host,
per-resolution artifact (a registry override changes it), so `devenv up` appends `env.sh`,
`logs/` and `.install-stamp` to `<root>/.devbox/.gitignore` (Decision Log, 2026-10-02 pre-flight).

**`reap`** (Interfaces §I3) — runs a command in its own process group as a child subreaper
(`prctl(PR_SET_CHILD_SUBREAPER)` on Linux; on macOS only a process-group owner), forwards
SIGTERM/SIGINT, waits, reaps every zombie it adopted, then terminates what is left in the group
(SIGTERM, 5 s, SIGKILL). Install scripts spawn daemons and watchers that outlive them, and zombies
from a killed install accumulate on a box that runs for months. Codex cloud ships the same tool as
`reap.py`.

**Sessions and seats in a project root** get the environment without any sminos change.
`claude --bg` forwards only an allowlisted environment to the already-running background daemon,
and a worker's environment is the daemon's plus that dispatch, so nothing sourced around the
launch reaches it. Two mechanisms carry it instead:
- the **shell-rc hook** (I6): `~/.claude/tools/devenv-rc.sh`, sourced from `~/.zshrc` and
  `~/.bashrc` (`sync/apply.py` appends the line idempotently on every host; the host layer's
  `seed.sh` runs `apply.py`, so the devbox gets it), sources `$PWD/.devbox/env.sh` when it exists.
  Only when `CLAUDECODE` is unset — the person's own login shells — does it also source
  `$PWD/.devbox/secrets.sh`, non-strict (a handler failure prints one value-free warning and the
  shell continues; it never breaks a login shell), so a daemon or `claude` started from such a
  shell inherits the secrets. Inside a Claude Code Bash shell (`CLAUDECODE=1`) it sources the
  non-secret env only: the sandbox denies the handler's key file to sandboxed commands (host
  layer), and a secret fetched inside a sandboxed shell would bypass masking. Claude Code snapshots the login shell at session start in the session's
  cwd, and a seat's worker does the same from its `--cwd`, so every Bash tool shell of a session
  or seat started in a project root carries the environment, whatever environment the daemon
  started with.
- **`settings.local.json` env** (I7): `devenv up` merges the NON-secret `env` into
  `<root>/.claude/settings.local.json`'s `env` block (other keys untouched), so the session process
  itself, its hooks and MCP servers see them. Secrets never go there.
`devenv claude/shell/start/validate` keep their explicit strict path: env.sh sourced, secrets
resolved in the launcher.

**Seats carry only global secrets (v1 limitation).** A seat's environment is the background
daemon's, so a seat holds only the secrets the daemon was started with: on the devbox the host
layer starts the daemon at boot with `GH_TOKEN` (its M4 records the route); on the Macs the daemon
inherits the login shell that first spawns (rc hook, outside Claude Code). Project-specific secrets
reach interactive sessions through `devenv claude` only; a seat that needs a project secret is not
supported in v1. Non-secret project env does reach seats — through the rc hook (Bash tool shells)
and `settings.local.json` (the session process).

## 4. The `cloud-env-setup` skill

`skills/cloud-env-setup/SKILL.md` in this repository: the agent's procedure to author or refresh
a project's environment, the way Codex's onboarding agent and Cursor's agent-led setup do, against
a persistent machine. Triggers: "set up the environment for this project", "write the environment
manifest", "cloud env", "environment.json", "install script for this repo". The procedure: inspect
the checkout (package managers and lockfiles, language runtimes, services and ports, test
commands, `.env.example` and CI config for the variables and secrets it needs, existing
`README`/`AGENTS.md`/`CLAUDE.md` run instructions); check what already works before asking for
anything (`compgen -e` for variable names, `git ls-remote` for access, `secret-env list` for known
secrets); draft `.devbox/environment.json`, `.devbox/install.sh` (with its `# devenv-inputs:`
line) and the start skill; run `devenv up` for real and fix until install passes; run
`devenv start` and `devenv validate` until the checks pass; commit the files; report what passed,
what needs a value only the human has (a secret to add to Secret Manager, named by the manifest's
`secrets[]` entry), and what remains. It writes fields as decisions, never placeholders (the
install script's steps are commands that ran). Written and tested with `doperpowers:writing-skills`.

## 5. What this is not

No per-session or per-project isolation beyond Claude Code's sandbox; no proxy of our own (the
sandbox's masking and allowlist are the enforcement, and only for sessions launched with the
generated `--settings`); no project-specific secrets in seats (§3 — per-seat project secrets need a
daemon-independent spawn path or a change to Claude Code's dispatch allowlist); no environment
snapshots or "publication"; no fleet-wide environment registry.
Each is named where the field that would need it is recorded.

## 6. Execution

### Constraints that bind every milestone

- **Two repositories.** `devenv`, `reap`, their tests, the registry directory and the manifests
  for the person's own repositories live in `claude-config` (`~/.claude` on the laptop), committed
  directly on its `main` (its sync rebases `main` every 30 minutes; each commit's short SHA goes in
  Progress). The skill, this spec and docs live in this repository on branch
  `project-env-manifest` in the isolated worktree `.claude/worktrees/project-env-manifest/`.
  Manifests for MAWS and claude-usage-menubar are committed in those repositories on a branch
  named `devbox-manifest` and pushed; merging them is the human's call.
- **Version bump** with the skill: `scripts/bump-version.sh` minor (a new skill), in the same
  commit, per this repository's convention.
- **Path identity:** `<GH>` = `/Users/new/Developer/GitHub` on every host; the tools never
  assume anything else.
- **Python 3.11 standard library only** for `devenv` and `reap`; the secret handler is invoked as
  a subprocess, never imported.
- **No secret value** in `env.sh`, logs, tests or transcripts; tests use a fake handler
  (`DEVENV_SECRET_ENV`, I1).
- **The person's checkouts are never moved, switched or written on the laptop.** Laptop runs of
  `devenv` happen in a scratch `<GH>` (`DEVENV_GH`) holding fresh clones or `git worktree`s on the
  manifest branches; acceptance items naming `<GH>` read as that scratch directory on the laptop
  and as the real `<GH>` on the devbox (E4).
- **Both OSes:** every `devenv`/`reap` behavior that can run on macOS is tested on the laptop;
  the Linux-only parts (`PR_SET_CHILD_SUBREAPER`) are guarded and tested on the devbox in E4.
- **Cross-spec dependency:** E4 needs the host layer's M3 (a devbox with `secret-env` and its
  key); E1–E3 run on the laptop and do not wait for it.
- **Testing:** `python3 -m unittest discover -s ~/.claude/tools/tests` for the tools; the skill is
  pressure-tested per `doperpowers:writing-skills`; acceptance 7 for the seat path; branch review at the medium rung (Decision Log).

### Plan of Work

#### E1 — Schema, resolution, `devenv up/claude/shell/show/list`, `env.sh`, `reap`

What exists at the end: `~/.claude/tools/devenv` and `~/.claude/tools/reap` on the laptop (and
through sync on the mini), unit tests for resolution and merge precedence and for `reap`'s
process cleanup, `<GH>/doperpowers/.devbox/environment.json` + `install.sh` (this repository is
the first project; its install is `npm ci` in `application-agents/triaging-feedback` plus
`tests/mods` staging as the README describes, idempotent), `~/.claude/envs/` created with a README
line, `!envs/`/`!envs/**` whitelisted in `~/.claude/.gitignore` in the same commit (verified by a
clean clone of claude-config carrying `envs/`), the `~/.local/bin` links from `sync/apply.py`
(verified from a fresh login shell), and acceptance 1, 2 (install-only subset), 3 (fake-backed),
6, 9 passing on the laptop. Touches: `~/.claude/tools/{devenv,reap}`,
`~/.claude/tools/tests/`, `~/.claude/envs/`, `~/.claude/.gitignore`, `~/.claude/sync/apply.py`,
`<GH>/doperpowers/.devbox/` (on the branch).
Decisions: `devenv` is one file (~600 lines) with a `Manifest` dataclass, `resolve(name)`,
`merge(repo_manifest, registry_entry)`, `write_env_sh`, `run_install`; subprocess calls go through
`reap` for install only; `git fetch` failures are warnings, clone failures are errors; the
install-skip fingerprint is §2's (tests: lockfile mutation reruns, lockfile deletion reruns,
registry override reruns, failed install leaves no stamp, `--force` reruns); env.sh's failure
semantics are I2's (tests: absent handler, denied/missing secret, stale variable); `devenv
claude` passes through all remaining arguments to `claude`; `devenv shell` passes `-c` through to
`$SHELL`. Does not touch: services, validate, the skill link, sminos, the skill. Proves:
acceptance 1, 2 (install-only subset), 3 (fake-backed), 6, 9.

#### E2 — `start/stop/status/validate`, the skill link, the rc hook and `settings.local.json` env

What exists at the end: services run in tmux with readiness, `validate` runs or prints,
`devenv up` links the start skill and writes the `settings.local.json` env (I7) and
`sandbox.settings.json` (I9), `devenv claude` passes it as `--settings`, the shell-rc hook
(I6) installed by `apply.py`, a seat spawned into a project root carries the environment;
acceptance 4, 5, 7 pass on the laptop (4 against MAWS's `pnpm dev`, which needs MAWS's manifest —
a minimal one is written here by hand and replaced by E3's skill-authored one). Touches:
`~/.claude/tools/devenv`, `~/.claude/tools/devenv-rc.sh`, `~/.claude/sync/apply.py` (the rc
line), `~/.claude/tools/tests/`, `<GH>/MAWS/.devbox/` (branch `devbox-manifest`); no sminos change.
Tests: a service started while a tmux server already runs reads a fake-backed variable from env.sh
inside the service child; the rc hook with a failing handler warns once, value-free, and the shell
continues, and under `CLAUDECODE=1` never calls the handler; `sandbox.settings.json` generation
for restricted/unrestricted, mask/deny and the Darwin `excludedCommands`, and its absence when
neither applies; `devenv claude` passing `--settings` only under `sandbox: true` or `--sandbox`; the placeholder halves of acceptance 3(iii) and the git-push-under-masking risk (§2)
checked on the laptop; the `settings.local.json` merge keeps other keys and never writes a secret;
`settings.local.json` is kept out of git (`.git/info/exclude` when the repository does not
already ignore it). Acceptance 7 is verified with the background daemon already running under a
different environment, for a spawn and for a resume. Decisions: tmux
session name = project name; `ready.http` uses `urllib` with a 3 s timeout polled every 2 s;
`status` prints `<service> running|exited` from `tmux list-panes` plus `ready yes|no`; `validate`
exits with `validate.sh`'s code. Does not touch: the skill. Proves: acceptance 2 (whole, with the
link), 4, 5, 7.

#### E3 — The `cloud-env-setup` skill and three real manifests

What exists at the end: `skills/cloud-env-setup/SKILL.md` (and its `references/` if the body
needs them), pressure-tested; manifests, install scripts and start skills for doperpowers (replacing
E1's hand-written one where the skill improves it), MAWS and claude-usage-menubar authored by
running the skill, each passing `devenv up`, `start` (where services exist) and `validate`;
acceptance 8 passes. Touches: `skills/cloud-env-setup/`, the version bump, the three repositories'
`.devbox/` (including `.devbox/skill/`) on their manifest branches. Decisions: the skill's
body follows this repository's skill voice ("your human partner"); its triggers are the five
phrases of §4; it writes `domains` for every secret it declares (the hosts the tool actually calls,
found from the repository's config) and sets `network.access` to `restricted` — with the package
registries and the secrets' hosts — when the project's install and tests reach a known, short list
of hosts, otherwise `unrestricted`; it refuses to write a secret value anywhere and names the Secret Manager entry
instead; the macOS-only project (claude-usage-menubar, Swift) gets an install script that checks
the Xcode toolchain and exits 0 with a message on Linux, and `validate.sh` runs `swift build` on
macOS only. Does not touch: the devbox. Proves: acceptance 8.

#### E4 — On the devbox, and the acceptance run

What exists at the end: on the devbox (host layer M3 done), `devenv up` for the three projects,
`devenv claude` through the relay, secrets through the handler's service-account key, `reap`'s
subreaper path tested on Linux, and acceptance 1–10 run as written with output recorded in
Concrete Steps. Touches: Concrete Steps of this spec; `~/.claude/tools/tests/` (a Linux-marked
test); a fixture project (registry entry or scratch `<GH>`) whose service is
`python3 -m http.server 8765`, standing in for MAWS's Electron dev server in acceptance 4. Before
the run, pre-existing clones are prepared per §2 (`repos[].ref`): clean → `git switch <ref>`,
dirty → stop and report. Decisions: the devbox gets the manifests by `devenv up` cloning the `devbox-manifest`
branches until the human merges them (`ref` in the registry entries points at those branches for
now; a Decision Log line records when `main` takes over). Does not touch: the host layer's files.
Proves: acceptance 10, and runs 1–9 again.

### Concrete Steps

Working directory: the laptop, `~/.claude` for the tools, the branch worktree for this
repository. Recorded with real transcripts as milestones complete.

E1 — run 2026-10-02 on the laptop, scratch `DEVENV_GH=/tmp/devenv-e1-acceptance/GH`, fake handler
(`DEVENV_SECRET_ENV`, value `FAKE-ghp-acceptance-not-a-token`); full transcripts in the E1 report.
```
$ python3 -m unittest discover -s ~/.claude/tools/tests      # Ran 87 tests … OK (58 devenv/reap + 29 secret-env)
$ devenv show doperpowers | jq .root                         # "/tmp/devenv-e1-acceptance/GH/doperpowers"
$ devenv show nosuch; echo rc=$?                             # no manifest for nosuch; run the cloud-env-setup skill in that repository / rc=1
$ devenv up doperpowers          # (<GH> empty) doperpowers: cloned doperpowers, install ok (log: …/.devbox/logs/install-20261003T033246Z.log)  rc=0, 7 s
$ devenv up doperpowers          # doperpowers: fetched, install skipped (unchanged)  rc=0, 0.58 s
$ devenv shell doperpowers -c 'echo $NODE_ENV; [ -n "$GH_TOKEN" ] && echo token-set'   # development / token-set
$ grep -rlF FAKE-ghp-acceptance-not-a-token <GH>/doperpowers/.devbox/; echo rc=$?       # rc=1 (logs included)
$ reap -- bash -c 'sleep 300 & exit 0'; pgrep -f "sleep 300" || echo clean            # reap: terminated 1 leftover process(es) / clean (0.23 s)
$ reap --timeout 2 -- sleep 300; echo rc=$?                  # reap: timed out after 2 s / rc=124 (2.22 s), sleep gone
$ DEVENV_REGISTRY=<scratch maws.json + NODE_ENV=test, MAWS ref master> devenv show maws | jq -c …
  {"root":".../GH/MAWS","repos":["MAWS","doperpowers"],"NODE_ENV":"test","secrets":["devbox-github-pat"],"install":null}
$ devenv up maws                 # maws: cloned MAWS; fetched doperpowers, no install script (doperpowers' install not run)
```
E2–E4: as the milestones state; recorded here when run.

### Interfaces and Dependencies

**I1 — `devenv`** (`~/.claude/tools/devenv`):
```
devenv up <name> [--force] [--url <https url> [--ref r]]
                                    clone/fetch repos, write env.sh, run install (skipped when unchanged), link the start skill;
                                    --url writes a single-repository registry entry first (§1)
devenv claude <name> [--sandbox] [args…]
                                    cd root; source env.sh; resolve secrets; exec claude [--settings <sandbox.settings.json>] args…
                                    (--settings when the manifest's `sandbox` is true or --sandbox is given)
devenv shell <name> [-c cmd]        cd root; source env.sh; exec $SHELL [-c cmd]
devenv start|stop|status <name>     services in tmux session <name>
devenv validate <name>              run <root>/.devbox/validate.sh, else print validation.md
devenv show <name>                  resolved manifest as JSON
devenv list                         registry entries and <GH>/*/.devbox/environment.json projects
```
Exit codes: 0 ok; 1 user error (no manifest, bad field) with one line on stderr; 2 install
failed (log tail on stderr); 3 service not ready within 120 s. Environment: `DEVENV_GH` overrides
`<GH>` (tests), `DEVENV_REGISTRY` overrides `~/.claude/envs` (tests), `DEVENV_SECRET_ENV` overrides
the handler path written into `env.sh` (default `/Users/new/.claude/tools/secret-env`; tests point
it at a fake).

**I2 — `env.sh` and `secrets.sh`** (generated; bash). `env.sh` carries non-secret env only:
```
# generated by devenv — do not edit; edit environment.json
export DEVENV_PROJECT='maws'
export DEVENV_ROOT='/Users/new/Developer/GitHub/MAWS'
export DEVENV_REPO_MAWS='/Users/new/Developer/GitHub/MAWS'
export DEVENV_REPO_DOPERPOWERS='/Users/new/Developer/GitHub/doperpowers'
export NODE_ENV='development'
```
`secrets.sh` holds the handler calls, never a value:
```
# generated by devenv — do not edit; edit environment.json
unset GH_TOKEN
_devenv_out="$('/Users/new/.claude/tools/secret-env' export devbox-github-pat:GH_TOKEN)" \
  || { echo "devenv: secret devbox-github-pat (GH_TOKEN) unavailable" >&2; unset _devenv_out; return 1; }
eval "$_devenv_out"; unset _devenv_out
```
Failure semantics: the handler's stdout is captured with its exit status, never
`eval "$(… 2>/dev/null)"`; a stale preexisting variable is unset first; on non-zero one line on
stderr names the secret (never a value) and the resolution fails, so `devenv
claude/shell/start/validate` refuse to proceed; the rc hook (I6) and `devenv up`'s install are the
non-strict callers. The launcher may resolve in Python or by sourcing `secrets.sh`; either way the
handler path comes from `DEVENV_SECRET_ENV` (default `/Users/new/.claude/tools/secret-env`, baked
into `secrets.sh` at generation) — the one injection point. `env.sh`, `secrets.sh` and
`sandbox.settings.json` are gitignored by `devenv up`. The exact shell is the implementer's; these
semantics bind.
`secret-env export <name>:<ENV>` is the host layer's I1 export with an explicit variable name
(the host layer's handler already maps `devbox-github-pat` → `GH_TOKEN`; the `:<ENV>` form is
added there by the host layer's executor, which owns `secret-env` — this spec never edits it; until
it lands, tests use a fake handler printing `export <ENV>=<value>` lines).

**I3 — `reap`** (`~/.claude/tools/reap`): `reap [--timeout SEC] [--grace SEC] -- cmd args…`;
exits with the command's code; 124 on timeout; prints `reap: terminated N leftover process(es)`
on stderr when it had to kill anything.

**I4 — Registry entry** (`~/.claude/envs/<name>.json`): the manifest schema of §2 with every
field optional except `name` and `repos`.

**I5 — Start-skill link:** each file of `<root>/<start_skill>/` (default `.devbox/skill`:
`SKILL.md`, `start.md`, `validation.md`) is linked as `<root>/.claude/skills/devenv/<file>`
(relative symlinks), so the skill's references to its sibling files resolve from the linked
location. Linking is a no-op only when `start_skill` is `.claude/skills/devenv` itself.

**I6 — shell-rc hook** (`~/.claude/tools/devenv-rc.sh`): sourced from `~/.zshrc` and
`~/.bashrc` by a line `sync/apply.py` appends idempotently; sources `$PWD/.devbox/env.sh` when it
exists, and `$PWD/.devbox/secrets.sh` only when `CLAUDECODE` is unset, non-strict — on failure one
value-free warning on stderr, and the shell continues.

**I7 — `settings.local.json` env:** `devenv up` merges the resolved non-secret `env` into
`<root>/.claude/settings.local.json` → `env` (other keys preserved); secrets never written.

**I9 — `sandbox.settings.json`** (`<root>/.devbox/sandbox.settings.json`, generated by `devenv up`;
§2 `network` and `secrets[]`): `{"sandbox": {"enabled": true, "network": {["allowedDomains": […],
"strictAllowlist": true,] ["tlsTerminate": {}]}, "credentials": {"envVars": [{"name": "GH_TOKEN",
"mode": "mask", "injectHosts": ["api.github.com", "github.com"]}, …]}, ["excludedCommands": [...]]}}`
— keys per Claude Code 2.1.283's sandbox settings; `devenv claude` passes it as `--settings` only
under `sandbox: true` or `--sandbox`.

**I8 — `cloud-env-setup` skill:** `skills/cloud-env-setup/SKILL.md`, frontmatter `name:
cloud-env-setup`, description with the five trigger phrases of §4.

## Surprises & Discoveries

- 2026-10-02 (E1): the laptop has no GitHub SSH key either (`ssh -T git@github.com` → publickey
  denied); HTTPS URLs are what make laptop clones work (doperpowers 7 s, MAWS 22 s).
- 2026-10-02 (E1): npm 12.1 blocks dependency install scripts unless allow-listed (`allowScripts`;
  esbuild ×2 and fsevents in triaging-feedback). The poller suite still passes 117/117 (esbuild
  ships its binary through optionalDependencies), but a project whose native modules need install
  scripts needs `npm install-scripts approve` or an `allowScripts` entry — E3's skill should know.
- 2026-10-02 (E1): the sibling's `secret-env` landed in claude-config (303bfcb); its `export`
  prints `export VAR=<shlex-quoted>`, matching env.sh's `eval` contract. Its tests share
  `tools/tests/`, so `discover` counts both suites.
- 2026-10-02 (E1): `/usr/bin/python3` is 3.9.6 and a minimal macOS PATH finds it through
  `#!/usr/bin/env python3`; the tools run on 3.9 as well as 3.11+ (only `glob(root_dir=)` was in
  the way).
- 2026-10-02 (E1): claude-config's 30-minute sync commits whatever is in the tree — 23c8586
  captured `tools/devenv` mid mutation-check; b84a386 restored it. Tool work in claude-config
  commits in small units and never leaves a deliberately broken file on disk longer than a test.
- 2026-10-02 (E1): MAWS's only remote branch is `master`. Upping a registry project whose root has
  no manifest yet leaves an untracked `.devbox/` (env.sh, .gitignore) in that root.

## Decision Log

- Decision: Verification — one independent spec review by the `doperpowers:adversarial-reviewer`
  agent (technical-heavy), the same agent's buildability review of the execution section (four
  milestones), and `doperpowers:review-code` at the **medium** rung on the branch at the end.
  Rationale: tools and a skill, bounded code volume, but they run on every host and touch sminos.
  Date/Author: 2026-10-02, the design session.
- Decision: manifests in the repository plus a personal registry; secrets injected as environment
  variables through the handler (proxy substitution deferred); network recorded, not enforced; no
  `tailscale` field. Rationale: the human's four answers on 2026-10-02 (grill round). Alternatives
  rejected then: registry-only (no sharing), repo-only (multi-repo awkward), proxy substitution now
  (an HTTPS-terminating proxy and a local CA for four secrets), per-seat network namespaces.
  Date/Author: 2026-10-02, the human.

- Decision (pre-flight, 2026-10-02, plan-executor): reconciling the spec with the codebase before E1.
  (a) sminos' seat launch is `run_claude_bg` in `sminos.py`, not `lib.sh` (which holds no launch);
  §3 and I6 now name it, the guarded source becoming a `bash -c` wrapper there, covering spawn and
  resume alike. (b) `secret-env` is owned by the host layer's executor, which adds the
  `export <name>:<ENV>` form; this spec never edits it, and env.sh's handler path is overridable at
  generation time (`DEVENV_SECRET_ENV`) so tests point at a fake. (c) A repository's own manifest
  cannot be resolved before that repository is cloned, so acceptance 2 (repo absent) and E4 (fresh
  devbox) need registry entries: `~/.claude/envs/` holds `doperpowers.json`, `maws.json` and
  `claude-usage-menubar.json`, refs pointing at the branches that carry the manifests
  (`project-env-manifest`, `devbox-manifest`) until the human merges them (MAWS's default branch is
  `master`, not `main`); `~/.claude/.gitignore` whitelists `envs/`. (d) doperpowers ignores
  `.claude/` wholesale, so its start skill lives in a committed `.devbox/skill/` and is linked;
  I5 links every start-skill file, not `SKILL.md` alone, so `start.md`/`validation.md` resolve.
  (e) env.sh is gitignored by `devenv up`: it carries a host path and registry overrides, so a
  committed copy would be dirtied by every resolution. (f) Laptop runs use a scratch `<GH>` with
  fresh clones / worktrees — the person's checkouts (claude-usage-menubar is on a working branch with
  untracked files) are never touched. (g) Acceptance 3's `grep "GH_TOKEN="` could never match the
  eval line it describes; restated as the eval line plus a grep for the (fake, on the laptop) value.
  (h) Acceptance 9 runs against a scratch `DEVENV_REGISTRY` copy of the real `maws.json` with the
  `NODE_ENV=test` override; the real entry carries none (it would change every real session's dev
  server).
- Decision (2026-10-02, the design session, confirming the pre-flight): the three registry entries
  are also what the devbox resolves through claude-config sync, so they stay minimal — `name`,
  `repos` (with refs), `root` — and their refs move to the default branches, with a dated line
  here, once the human merges the manifest branches.

- Decision (2026-10-02, plan-executor folding the execution-section buildability review): (1) the
  `envs/` whitelist lands in the claude-config commit that creates the registry, verified by a
  clean clone; (2) the host layer has added `secret-env export <name>:<ENV>`, `run <name>:<ENV>`
  and `list` to its I1 (its commit d464bd2f); the executable lands with its M1 — until then every
  laptop test is fake-backed through `DEVENV_SECRET_ENV`, the single injection point the CLI and
  env.sh share, and acceptance 3's real-handler run is deferred to "handler present" (at the latest
  E4); (3) env.sh's failure semantics (I2): captured status, stale variable unset, one stderr line
  naming the secret, non-zero return so callers refuse; (4) `.devbox/skill/` is the default
  start-skill source for every repository, superseding the earlier per-repository wording, with a
  no-op only when source and destination coincide (§2, I5, acceptance 8); (5) manifest refs point
  at the manifest branches until merged; existing checkouts stay fetch-only, with E4's preparation
  step (clean → switch, dirty → stop) for pre-existing clones; (6) tmux service windows source
  env.sh themselves, tested against an already-running tmux server; (7) acceptance 4 is a macOS
  check against MAWS (electron-vite needs a display), with an `http.server` fixture proving it on
  the devbox; (8) the install fingerprint is defined in §2 with five named tests; (9) E1 proves
  acceptance 2's install-only subset and E2 the whole item; acceptance 3 split into (i)–(iii);
  (10) `sync/apply.py` installs `~/.local/bin/{devenv,reap}` symlinks, verified from a fresh login
  shell; (11) sminos' change is tested through `run-sminos-tests.sh` with `launch_env`'s filtering
  preserved. Rationale: the review's findings, each a real gap between the spec and what would
  build or hold on a second host.

- Decision (2026-10-02, plan-executor folding the design review of Purpose–§5): (1) seat
  environment: `claude --bg` forwards only an allowlisted environment to the running background
  daemon (verified by the reviewer in the 2.1.283 bundle), so pre-flight (a)'s `run_claude_bg`
  wrapper could never deliver acceptance 7 — reversed: no sminos change; a shell-rc hook (I6) plus
  `settings.local.json` env (I7) carry the environment, and the skill moves to I8. (2) Multi-repo
  composition is root-only: install, start skill, services and validate from the root (or the
  registry); non-root repositories contribute `env` and `secrets` only, in list order, then root,
  then registry; `DEVENV_REPO_<NAME>` exported for every repository. (3) Repository URLs are HTTPS
  (the devbox authenticates GitHub through `gh auth setup-git`, with no SSH key); `git@github.com:`
  normalized. (4) Cold start: clonable by name only through a registry entry; `devenv up --url`
  writes one. Rationale: the review's findings — (1) is a mechanism that could not have worked.

- Decision (2026-10-02, E1 executor, folded by the controller): `devenv` details the spec left
  open — repository manifests ignore `name`/`root` (the requested name is the project; a registry
  entry's `name` must match its file); unknown top-level fields, non-string `env` values and
  non-identifier variable names are exit-1 errors (E2 adds `validate` to the known keys); `show`
  prints the resolved manifest with defaults filled in, and that JSON is fingerprint part (a);
  registry-mode repo order is the entry's, then any extra repos the root manifest names, re-resolved
  after each clone pass; clone failure exits 1 and a failed first `ref` checkout removes the fresh
  clone; the stamp is deleted before every install run; `devenv claude`/`shell` regenerate env.sh
  before sourcing; `--url` refuses an existing different entry; reap counts leftovers via `/proc`
  or `ps` with zombies excluded, and devenv waits through Ctrl-C while reap cleans its group.
  doperpowers' install is `npm ci` in triaging-feedback (the mods suite stages itself per run, so
  there is nothing to pre-stage), and its start skill was hand-written into `.devbox/skill/` in E1
  so E2 can prove acceptance 2 whole.

- Decision (2026-10-02, the human; folded by the plan-executor): the manifest's `network` and
  `secrets[].domains` drive Claude Code's native sandbox (verified in 2.1.283's sandbox settings:
  `allowedDomains` + `strictAllowlist`, `credentials.envVars` mask/deny with `injectHosts`,
  `tlsTerminate`, `excludedCommands`; masking only from user/managed settings or `--settings`).
  Supersedes "network recorded, not enforced" and the deferral of proxy substitution in the
  2026-10-02 grill-round entry. Consequences: `devenv up` writes `sandbox.settings.json` (I9);
  `devenv claude` passes it; seats get it through `sminos spawn --settings`; secrets enter at
  launch only — env.sh is non-secret, `secrets.sh` holds the handler calls, the rc hook resolves
  secrets only outside Claude Code (the sandbox denies the handler's key file, and an in-sandbox
  fetch would bypass masking); acceptance 3 and 7 test the placeholder. Controller's call within
  it: `devenv up`'s install resolves secrets non-strictly (warns and runs without an unavailable
  one), reversing E1's strict install sourcing — an install that needs no secret must not fail on
  a host without the handler, and the cloud-env-setup flow reports a missing secret rather than
  failing on it. E1's env.sh secret lines move to `secrets.sh` in E1's fix wave; sandbox settings
  generation is E2.

- Decision (2026-10-02, the human; folded by the plan-executor): "even without the native
  sandbox, relying on the auto classifier is almost sufficient." The sandbox is opt-in and never
  blocking: `sandbox.settings.json` is generated when `access: restricted` or any secret has
  `domains`; `devenv claude` applies it only under the manifest's `sandbox: true` (new optional
  boolean, default false) or `--sandbox`; otherwise the host's default settings and the auto
  classifier govern. Secrets still enter only at launch. Acceptance 3's mask/injection checks run
  only where the sandbox is opted into; unconditionally, the variable is present in the session and
  no value is on disk. Friction under masking in E2/E4 is recorded and leaves `sandbox` false.

- Decision (2026-10-02, the design session): `devenv up`'s install resolves secrets non-strictly
  (confirmed). Seats carry only global secrets — the daemon's environment — and project-specific
  secrets reach interactive sessions through `devenv claude` only (§3, §5); acceptance 7's
  placeholder check is conditional on the seat holding `GH_TOKEN`, its NODE_ENV check proves the
  non-secret path. Per-seat project secrets are residue for a ticket.

## Outcomes & Retrospective

Pending — written at finish.
