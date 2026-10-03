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
- [ ] E2 — `devenv start/stop/status/validate`, the start-skill link, sminos sources `env.sh`
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
   `<GH>/doperpowers/.claude/skills/devenv/SKILL.md`; a second `devenv up doperpowers` finishes in
   under 15 s and reports `fetched, install skipped (unchanged)`.
3. **Environment and secrets.** `devenv shell doperpowers -c 'echo $NODE_ENV; [ -n "$GH_TOKEN" ] && echo token-set'`
   prints `development` and `token-set`; env.sh's only `GH_TOKEN` line reads
   `eval "$(…secret-env export devbox-github-pat:GH_TOKEN …)"`, and `grep -rlF "<the token value>" <GH>/doperpowers/`
   finds nothing (the value is never on disk; amended 2026-10-02, Decision Log).
4. **Services.** `devenv start maws` creates tmux session `maws` with window `dev` and prints
   `dev: ready (http://127.0.0.1:5173/)` within 120 s; `devenv status maws` lists `dev running`;
   `devenv stop maws` ends the session and `tmux has-session -t maws` fails.
5. **Validation.** `devenv validate doperpowers` runs `.devbox/validate.sh` and prints
   `validate: pass` (exit 0); in a project with only `validation.md` it prints that checklist and
   exits 0 with `validate: checklist printed (no validate.sh)`.
6. **Reap.** `reap -- bash -c 'sleep 300 & exit 0'` returns within 10 s and `pgrep -f "sleep 300"`
   finds nothing; `reap --timeout 2 -- sleep 300` exits 124 and the sleep is gone.
7. **Seats inherit.** `sminos spawn envtest "print the value of NODE_ENV and stop" --cwd <GH>/doperpowers --wait`
   replies with `development`.
8. **Onboarding by skill.** In `<GH>/claude-usage-menubar` (no manifest yet), the `cloud-env-setup`
   skill produces `.devbox/environment.json`, `.devbox/install.sh`,
   `.claude/skills/devenv/start.md` and `validation.md`, and `devenv up claude-usage-menubar`
   passes on the first run after the skill finishes.
9. **Registry composition.** With `~/.claude/envs/maws.json` naming repos `MAWS` and `doperpowers`
   and overriding `env.NODE_ENV` to `test`, `devenv show maws` prints `root` = `<GH>/MAWS`, both
   repos, and `NODE_ENV: test`; the unit tests for merge precedence pass
   (`python3 -m unittest discover -s ~/.claude/tools/tests`).
10. **On the devbox.** `devenv list` names the three projects; `devenv up` for each passes;
    `devenv claude doperpowers -p 'reply with the word pong'` prints `pong`; item 3 holds there
    with the handler's service-account key.

## 1. Where a manifest lives (the human's decision)

Two places, composed:

- **In the repository**, `<repo>/.devbox/environment.json`, versioned with the code it serves
  (Cursor's lesson: environment drift is the standing wound, and a spec beside the code drifts
  least). A single-repository project needs nothing else; its name is the repository's directory
  name under `<GH>`.
- **In the personal registry**, `~/.claude/envs/<name>.json` (synced by `claude-config`): names a
  project that spans several repositories, pins which repositories and refs belong to it, and
  carries personal overrides (an extra variable, a different install timeout, a local port). The
  registry entry wins on collision, field by field; the lists `repos`, `secrets` and `services`
  merge by `name` with the registry's entry replacing the repository's entry of the same name.

Resolution for `devenv <cmd> <name>`: the registry entry if present; else
`<GH>/<name>/.devbox/environment.json`; else exit 1 with
`no manifest for <name>; run the cloud-env-setup skill in that repository`. A registry entry's
repositories each contribute their own `.devbox/environment.json` (install, start skill, env,
secrets, services) when present; the entry's fields override the merged result. The repository
named by `root` (default: the first) is the project root.

## 2. The manifest

```json
{
  "version": 1,
  "name": "maws",
  "repos": [
    {"name": "MAWS", "url": "git@github.com:SSFSKIM/MAWS.git", "ref": "main"},
    {"name": "doperpowers", "url": "git@github.com:SSFSKIM/doperpowers.git", "ref": "main"}
  ],
  "root": "MAWS",
  "install": {"script": ".devbox/install.sh", "timeout_sec": 1800},
  "start_skill": ".claude/skills/devenv",
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
  is the ssh form; git authenticates with the host's key.
- `root`: the project root by repository `name`; default the first repository. In a repository's
  own manifest `root` is implied.
- `install.script`: path relative to root; run through `reap` with `timeout_sec` (default 1800)
  and a log at `<root>/.devbox/logs/install-<UTC ts>.log`; must be idempotent (Cursor and Codex
  both make this the contract that makes refresh safe). Exit non-zero fails `devenv up` with the
  log's last 40 lines on stderr. `devenv up` skips install when the script, the manifest and every
  lockfile the script names in a leading `# devenv-inputs: <glob>…` comment are unchanged since
  the last successful run (a hash recorded in `<root>/.devbox/.install-stamp`); `--force` reruns.
- `start_skill`: a directory relative to root holding `start.md` and `validation.md`. `devenv up`
  writes `<root>/.claude/skills/devenv/SKILL.md` as a symlink to `<start_skill>/SKILL.md`, which
  the skill author writes with frontmatter (`name: devenv`, description "Use when starting,
  running, or validating this project's development workflow") and a body that is `start.md`'s
  content pointing at `validation.md`. Claude Code loads it as a project skill.
- `services[]`: optional. `devenv start` opens tmux session `<name>` with one window per service
  running `cmd` in `cwd` (relative to root), then waits up to 120 s for `ready` (`http`: GET
  returning 2xx/3xx; `tcp`: `host:port` accepting) and prints one line per service; `devenv stop`
  kills the session; `devenv status` lists windows and whether each `ready` check passes now.
- `network`: recorded, not enforced (the human's decision: unrestricted; the agents and the auto
  classifier are trusted). `access` ∈ `unrestricted` | `restricted`; `allowed_domains` is what a
  future per-project proxy would enforce. `devenv up` prints a one-line warning when `restricted`
  is set.
- `env`: non-secret variables, written into `env.sh` literally (shell-quoted).
- `secrets[]`: `name` is the Secret Manager name (host layer §5), `env` the variable; `domains`
  is recorded for the future proxy-substitution mode and unused now. `env.sh` resolves them at
  source time through the handler, so no value is ever on disk; the agent can read them in its
  environment (accepted for v1; the alternative — placeholders substituted by an HTTPS-terminating
  proxy with a local CA, Codex's "network secrets" — is the named follow-up).
- No `tailscale` field: the auth key is a host-layer concern.

## 3. The tools

All live in `claude-config` (`~/.claude/tools/`, synced to every host): python 3.11, standard
library only (plus calling `secret-env`), one file each, executable, with tests under
`~/.claude/tools/tests/`.

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

**sminos** — the seat launch path (`run_claude_bg` in `skills/sminos/scripts/sminos.py`, through
which every `claude --bg` spawn and resume goes) sources `<cwd>/.devbox/env.sh` when it exists, in
a bash subshell that then execs `claude`, so a seat spawned into a project root gets the project's
environment. One guarded change; no other sminos change; its test lives in
`tests/sminos/run-sminos-tests.sh` (Decision Log, 2026-10-02 pre-flight).

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

No per-session or per-project isolation; no network enforcement; no secret placeholder
substitution; no environment snapshots or "publication"; no fleet-wide environment registry.
Each is named where the field that would need it is recorded.

## 6. Execution

### Constraints that bind every milestone

- **Two repositories.** `devenv`, `reap`, their tests, the registry directory and the manifests
  for the person's own repositories live in `claude-config` (`~/.claude` on the laptop), committed
  directly on its `main` (its sync rebases `main` every 30 minutes; each commit's short SHA goes in
  Progress). The skill, the sminos line, this spec and docs live in this repository on branch
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
  pressure-tested per `doperpowers:writing-skills`; sminos' existing test runner for the line
  there; branch review at the medium rung (Decision Log).

### Plan of Work

#### E1 — Schema, resolution, `devenv up/claude/shell/show/list`, `env.sh`, `reap`

What exists at the end: `~/.claude/tools/devenv` and `~/.claude/tools/reap` on the laptop (and
through sync on the mini), unit tests for resolution and merge precedence and for `reap`'s
process cleanup, `<GH>/doperpowers/.devbox/environment.json` + `install.sh` (this repository is
the first project; its install is `npm ci` in `application-agents/triaging-feedback` plus
`tests/mods` staging as the README describes, idempotent), `~/.claude/envs/` created with a README
line, and acceptance 1, 2, 3, 6, 9 passing on the laptop. Touches: `~/.claude/tools/{devenv,reap}`,
`~/.claude/tools/tests/`, `~/.claude/envs/README.md`, `<GH>/doperpowers/.devbox/` (on the branch).
Decisions: `devenv` is one file (~600 lines) with a `Manifest` dataclass, `resolve(name)`,
`merge(repo_manifest, registry_entry)`, `write_env_sh`, `run_install`; subprocess calls go through
`reap` for install only; `git fetch` failures are warnings, clone failures are errors; the
install-skip hash covers the manifest, the script, and the `# devenv-inputs:` globs; `devenv
claude` passes through all remaining arguments to `claude`; `devenv shell` passes `-c` through to
`$SHELL`. Does not touch: services, validate, the skill link, sminos, the skill. Proves:
acceptance 1, 2, 3, 6, 9.

#### E2 — `start/stop/status/validate`, the skill link, sminos sources `env.sh`

What exists at the end: services run in tmux with readiness, `validate` runs or prints,
`devenv up` links the start skill, a seat spawned into a project root carries the environment;
acceptance 4, 5, 7 pass on the laptop (4 against MAWS's `pnpm dev`, which needs MAWS's manifest —
a minimal one is written here by hand and replaced by E3's skill-authored one). Touches:
`~/.claude/tools/devenv`, `~/.claude/tools/tests/`, `skills/sminos/scripts/lib.sh` (one guarded
`source` line), sminos' tests, `<GH>/MAWS/.devbox/` (branch `devbox-manifest`). Decisions: tmux
session name = project name; `ready.http` uses `urllib` with a 3 s timeout polled every 2 s;
`status` prints `<service> running|exited` from `tmux list-panes` plus `ready yes|no`; `validate`
exits with `validate.sh`'s code. Does not touch: the skill. Proves: acceptance 4, 5, 7.

#### E3 — The `cloud-env-setup` skill and three real manifests

What exists at the end: `skills/cloud-env-setup/SKILL.md` (and its `references/` if the body
needs them), pressure-tested; manifests, install scripts and start skills for doperpowers (replacing
E1's hand-written one where the skill improves it), MAWS and claude-usage-menubar authored by
running the skill, each passing `devenv up`, `start` (where services exist) and `validate`;
acceptance 8 passes. Touches: `skills/cloud-env-setup/`, the version bump, the three repositories'
`.devbox/` and `.claude/skills/devenv/` on their `devbox-manifest` branches. Decisions: the skill's
body follows this repository's skill voice ("your human partner"); its triggers are the five
phrases of §4; it refuses to write a secret value anywhere and names the Secret Manager entry
instead; the macOS-only project (claude-usage-menubar, Swift) gets an install script that checks
the Xcode toolchain and exits 0 with a message on Linux, and `validate.sh` runs `swift build` on
macOS only. Does not touch: the devbox. Proves: acceptance 8.

#### E4 — On the devbox, and the acceptance run

What exists at the end: on the devbox (host layer M3 done), `devenv up` for the three projects,
`devenv claude` through the relay, secrets through the handler's service-account key, `reap`'s
subreaper path tested on Linux, and acceptance 1–10 run as written with output recorded in
Concrete Steps. Touches: Concrete Steps of this spec; `~/.claude/tools/tests/` (a Linux-marked
test). Decisions: the devbox gets the manifests by `devenv up` cloning the `devbox-manifest`
branches until the human merges them (`ref` in the registry entries points at those branches for
now; a Decision Log line records when `main` takes over). Does not touch: the host layer's files.
Proves: acceptance 10, and runs 1–9 again.

### Concrete Steps

Working directory: the laptop, `~/.claude` for the tools, the branch worktree for this
repository. Recorded with real transcripts as milestones complete.

E1
```
python3 -m unittest discover -s ~/.claude/tools/tests            # OK (N tests)
devenv show doperpowers | jq .root                                 # "/Users/new/Developer/GitHub/doperpowers"
mv <GH>/doperpowers <GH>/doperpowers.aside && devenv up doperpowers && mv … back  # (in a scratch GH dir for the test)
devenv up doperpowers                                              # fetched, install skipped (unchanged)
devenv shell doperpowers -c 'echo $NODE_ENV'                       # development
reap -- bash -c 'sleep 300 & exit 0'; pgrep -f "sleep 300" || echo clean   # clean
```
E2–E4: as the milestones state; recorded here when run.

### Interfaces and Dependencies

**I1 — `devenv`** (`~/.claude/tools/devenv`):
```
devenv up <name> [--force]          clone/fetch repos, write env.sh, run install (skipped when unchanged), link the start skill
devenv claude <name> [args…]        cd root; source env.sh; exec claude args…
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

**I2 — `env.sh`** (generated; bash):
```
# generated by devenv — do not edit; edit environment.json
export DEVENV_PROJECT='maws'
export DEVENV_ROOT='/Users/new/Developer/GitHub/MAWS'
export NODE_ENV='development'
eval "$(/Users/new/.claude/tools/secret-env export devbox-github-pat:GH_TOKEN 2>/dev/null)"
```
`secret-env export <name>:<ENV>` is the host layer's I1 export with an explicit variable name
(the host layer's handler already maps `devbox-github-pat` → `GH_TOKEN`; the `:<ENV>` form is
added there by the host layer's executor, which owns `secret-env` — this spec never edits it; until
it lands, tests use a fake handler printing `export <ENV>=<value>` lines).

**I3 — `reap`** (`~/.claude/tools/reap`): `reap [--timeout SEC] [--grace SEC] -- cmd args…`;
exits with the command's code; 124 on timeout; prints `reap: terminated N leftover process(es)`
on stderr when it had to kill anything.

**I4 — Registry entry** (`~/.claude/envs/<name>.json`): the manifest schema of §2 with every
field optional except `name` and `repos`.

**I5 — Start-skill link:** each file of `<root>/<start_skill>/` (`SKILL.md`, `start.md`,
`validation.md`) is linked as `<root>/.claude/skills/devenv/<file>` (relative symlinks), so the
skill's references to its sibling files resolve from the linked location. When `start_skill` is
`.claude/skills/devenv` itself (the default) nothing is linked and `devenv up` only checks that
`SKILL.md` exists.

**I6 — sminos:** `run_claude_bg` in `skills/sminos/scripts/sminos.py`: when `<cwd>/.devbox/env.sh`
exists, the launch is `bash -c '. "$1"; shift; exec claude "$@"' devenv <cwd>/.devbox/env.sh <args…>`
instead of `claude <args…>`; otherwise unchanged.

**I7 — `cloud-env-setup` skill:** `skills/cloud-env-setup/SKILL.md`, frontmatter `name:
cloud-env-setup`, description with the five trigger phrases of §4.

## Surprises & Discoveries

(none yet)

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

## Outcomes & Retrospective

Pending — written at finish.
