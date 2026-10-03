# Project environment manifests — design

**Date.** 2026-10-02. **Status.** Presented for approval; routes to doperpowers:execspec as a
sibling spec of `2026-10-02-personal-cloud-env-design.md` (it consumes that spec's devbox and its
`secret-env` interface I1; nothing in it changes M0–M6 there).

## 1. Purpose

The host layer makes the devbox *the person's computer*. This layer makes each **project** ready
on any of the person's computers the same way: one declaration per project says which
repositories it is made of, how to install it, how to start and check it, what environment and
which secrets it needs. A session that opens on the project finds it installed, its services
startable from one command, and its secrets in the environment without ever having been written
to a file. The same declaration drives the devbox and the two Macs, because every host has the
same paths.

What someone can do after: `devenv up maws` on a fresh devbox clones the project's repositories
under `/Users/new/Developer/GitHub/`, runs the project's install script to completion with a
log, and leaves `.devbox/env.sh`; `devenv claude maws` starts a session in the project root with
`GH_TOKEN` and the project's variables set; `devenv start maws` brings the project's services up
in a tmux session and waits until each one answers; a session working in the project sees a
`devenv` project skill with `start.md` and `validation.md` and knows how to run and check the
app; and the `cloud-env-setup` skill lets an agent author or refresh all of this for a project it
has never seen, by inspecting the repository and running the install for real.

The model is Codex cloud's environment (install_script, start_skill, allowed domains, environment
variables, proxy-substituted secrets) and Cursor's `environment.json` (install, start, terminals),
re-cut for one person's persistent machines: no publication step, no snapshot cache — the home
persists, so install is idempotent and "refresh" is `devenv up` again.

Terms: **manifest** — `environment.json`; **registry** — `~/.claude/envs/`; **project root** —
the directory `devenv` treats as the working directory (the first repository's path, or the
registry entry's `root`); **install** — the idempotent script that makes the checkout buildable;
**start skill** — the markdown instructions a session reads to run and check the project.

## 2. Where a manifest lives (the human's decision)

Two places, composed:

- **In the repository**, `<repo>/.devbox/environment.json`, versioned with the code it serves
  (Cursor's lesson: environment drift is the standing wound, and a spec beside the code drifts
  least). A single-repository project needs nothing else; its name is the repository's directory
  name.
- **In the personal registry**, `~/.claude/envs/<name>.json` (synced by `claude-config`): names a
  project that spans several repositories, pins which repositories and refs belong to it, and
  carries personal overrides (an extra env var, a different install timeout, a local service
  port). The registry entry wins on collision, field by field; lists (`repos`, `secrets`,
  `services`) merge by `name`.

Resolution for `devenv <cmd> <name>`: the registry entry if present; else the repository at
`/Users/new/Developer/GitHub/<name>/.devbox/environment.json`; else error "no manifest for
<name>; run the cloud-env-setup skill in that repository".

## 3. The manifest

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
    {"name": "dev", "cmd": "pnpm dev", "ready": {"http": "http://127.0.0.1:5173/"}, "cwd": "."}
  ],
  "network": {"access": "unrestricted", "allowed_domains": []},
  "env": {"NODE_ENV": "development"},
  "secrets": [
    {"name": "devbox-github-pat", "env": "GH_TOKEN", "domains": ["api.github.com", "github.com"]}
  ]
}
```

Field semantics (each is a decision):
- `repos[]`: cloned or fetched to `/Users/new/Developer/GitHub/<name>` on every host; `ref` is
  checked out only on first clone — afterwards the checkout is the person's working tree and
  `devenv up` only fetches. `url` is the ssh form; git authenticates with the host's key (the
  devbox's key is authorized on GitHub in the host layer's M3; on the Macs the existing keys).
- `root`: the project root; default the first repository.
- `install.script`: path relative to root; run by `reap` (below) with `timeout_sec` (default
  1800) and a log at `<root>/.devbox/logs/install-<UTC ts>.log`; must be idempotent (Cursor and
  Codex both make this the contract that lets refresh and cache misses be safe). Exit non-zero
  fails `devenv up` with the log's last 40 lines.
- `start_skill`: a directory holding `start.md` and `validation.md`; `devenv up` links it to
  `<root>/.claude/skills/devenv/SKILL.md` (frontmatter generated: name `devenv`, description
  "Use when starting, running, or validating this project's development workflow") so Claude Code
  loads it as a project skill; `start.md` is the body, `validation.md` is referenced from it.
- `services[]`: optional; `devenv start` opens tmux session `<name>` with one window per service
  running `cmd` in `cwd` (relative to root), then waits up to 120 s for `ready` (`http` GET
  returning 2xx/3xx, or `tcp` host:port accepting) and reports; `devenv stop` kills the session.
  `start.md` may simply say "run `devenv start`".
- `network`: recorded, not enforced (the human's decision: unrestricted, the agents and the auto
  classifier are trusted). `access` ∈ `unrestricted` | `restricted`; `allowed_domains` is the
  list a future per-project proxy would enforce. `devenv up` warns when `restricted` is set that
  enforcement is not implemented.
- `env`: non-secret variables, written into `env.sh` literally.
- `secrets[]`: `name` is the Secret Manager name (host layer §5), `env` the variable; `domains`
  is recorded for the future proxy-substitution mode and unused now. `env.sh` resolves them at
  source time through the secret handler (`eval "$(secret-env export <name>:<ENV>)"`), so no
  value is ever on disk; the agent can read them in its environment (accepted for v1; the
  alternative — placeholders substituted by an HTTPS-terminating proxy with a local CA, Codex's
  "network secrets" — is the named follow-up).
- Removed from the human's first list: a `tailscale` field. The auth key is a host-layer concern
  (the devbox is already on the tailnet); nothing per project.

## 4. The tools

All live in `claude-config` (`~/.claude/tools/`, synced to every host), python 3.11, no
dependencies beyond the standard library and the existing `secret-env`.

**`devenv`** — `up <name>` (resolve, clone/fetch, write `env.sh`, run install, link the skill;
idempotent), `claude <name> [claude args…]` (cd root, source `env.sh`, `exec claude`),
`shell <name>` (same with `$SHELL`), `start <name>` / `stop <name>` / `status <name>` (services
in tmux), `validate <name>` (runs `<root>/.devbox/validate.sh` when present and prints
`validation.md`'s checklist for the agent otherwise), `list` (registry + repositories with a
manifest), `show <name>` (the resolved manifest as JSON). `env.sh` is written to
`<root>/.devbox/env.sh` and is safe to commit (it holds only non-secret values and `secret-env`
calls); `.devbox/logs/` is gitignored by `devenv up` (it appends to `<root>/.devbox/.gitignore`).

**`reap`** — `reap [--timeout N] -- cmd…`: runs the command in its own process group as a child
subreaper (`prctl(PR_SET_CHILD_SUBREAPER)` on Linux; on macOS it is only a process-group owner),
forwards SIGTERM/SIGINT, waits, then reaps every zombie it has adopted and terminates anything
left in the group (SIGTERM, 5 s, SIGKILL). It exists because install scripts spawn daemons and
watchers that outlive them and because zombies from a killed install accumulate on a box that
runs for months. Codex cloud ships the same tool as `reap.py`.

**sminos integration** — the seat spawn path (`skills/sminos/scripts/lib.sh`) sources
`<cwd>/.devbox/env.sh` when it exists before launching `claude --bg`, so a seat spawned into a
project root gets the project's environment without going through `devenv claude`. One guarded
line; no other sminos change.

## 5. The `cloud-env-setup` skill

`skills/cloud-env-setup/SKILL.md` in this repository: the agent's procedure to author or refresh
a project's environment, the way Codex's onboarding agent and Cursor's agent-led setup do, but
against a persistent machine. It triggers on "set up the environment for this project", "write
the environment manifest", "cloud env", "environment.json", "install script for this repo". The
procedure: inspect the checkout (package managers and lockfiles, language runtimes, services and
ports, test commands, `.env.example` and CI config for the variables and secrets it needs,
existing `README`/`AGENTS.md`/`CLAUDE.md` run instructions); check what already works before
asking for anything (`compgen -e` for variable names, `git ls-remote` for access, the secret
handler's `list` for known secrets); draft `.devbox/environment.json`, `.devbox/install.sh` and
the start skill (`start.md`, `validation.md`); run `devenv up` for real and fix until install
passes; run `devenv start` and `devenv validate` until the checks pass; commit the files; report
what passed, what needs a value only the human has (a secret to add to Secret Manager, named by
the manifest's `secrets[]` entry), and what remains. It writes the manifest's fields as decisions,
never placeholders (the install script's steps are real commands that ran). Written and tested
with `doperpowers:writing-skills`, like every skill here.

## 6. What this is not

No per-session or per-project isolation; no network enforcement; no secret placeholder
substitution; no environment snapshots or "publication" (the home persists; `devenv up` is the
refresh); no fleet-wide environment registry. Each is named where the field that would need it is
recorded.

## 7. Silent decisions

JSON over TOML (Claude Code and Cursor both use JSON for this); registry entries are plain files
so the existing `claude-config` sync carries them; `env.sh` is bash and sourced by bash/zsh;
`devenv` refuses to run install when the root has uncommitted changes to tracked files it would
touch only if the manifest says so (it does not inspect the tree); services run in tmux rather
than systemd because they are per-person, per-session things and tmux is on every host; the
skill link is a symlink so the repository's start skill stays the source.

## 8. Plan of work (outline for execspec)

| # | Milestone | Outcome |
|---|---|---|
| E1 | Manifest schema, resolution (repo + registry merge), `devenv up/claude/shell/show/list`, `env.sh`, `reap`; unit tests for resolution and merge; integration on the laptop with this repository as the project | a project installs and a session opens in it from one command on a Mac |
| E2 | `devenv start/stop/status/validate`, the start-skill link, sminos env.sh sourcing | services and checks from one command; seats inherit the environment |
| E3 | `cloud-env-setup` skill, written and tested with writing-skills; first real manifests for doperpowers, MAWS and claude-usage-menubar authored by the skill | an agent can onboard a project |
| E4 | On the devbox (after the host layer's M3): `devenv up` for the three projects, `devenv claude`, secrets through `secret-env`; acceptance run | the same projects ready on the cloud home |
