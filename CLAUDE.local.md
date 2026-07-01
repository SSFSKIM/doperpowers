# CLAUDE.local.md — fork working notes

> **Why this file exists.** The tracked `CLAUDE.md` in this repo belongs to
> upstream (`obra/superpowers`) — it is their PR-contributor guide, and
> `AGENTS.md` is a symlink to it. Editing that file would create a merge
> conflict on **every** upstream sync. This fork's own guidance therefore lives
> here in `CLAUDE.local.md` (Claude Code auto-loads it). A fork-only *new* file
> never conflicts with upstream, so this is the sync-safe place for it.
>
> Note: `CLAUDE.local.md` is read by Claude Code but **not** by Codex/other
> harnesses (those read `AGENTS.md` → `CLAUDE.md`). If you drive this repo from
> Codex, mirror anything critical there or keep Codex to reviewer-subagent use.

## What this repo is

`doperpowers` is a **personal fork of `obra/superpowers`** — a multi-harness
plugin (mostly *skills*) that gives coding agents a full software-development
methodology (brainstorm → worktree → plan → subagent-driven TDD → review →
finish). The skills auto-trigger via a session-start bootstrap; you rarely
invoke them by hand.

Two goals for this fork:
1. **Customize** the plugin to how I actually work.
2. **Stay in good-sync with upstream.**

Those goals are in tension. The rule below keeps them compatible.

## The golden rule: minimize & intend every divergence

Upstream owns the tracked files. Every edit you make to an upstream-tracked file
is a future merge conflict. So:

- **Prefer additive, fork-only files** (new files upstream doesn't have) — they
  never conflict. This file is an example.
- **Edit upstream-tracked files only when the customization genuinely requires
  it**, and keep the diff small and self-contained (easier conflict resolution).
- Keep fork-specific commits **small and well-described** so they replay cleanly
  during a sync/rebase.

## Remotes & sync workflow

```
origin    → https://github.com/SSFSKIM/doperpowers.git   (this fork)
upstream  → https://github.com/obra/superpowers.git        (source of truth)
```

Upstream ships releases on `main` (tags `vX.Y.Z`); active upstream work lands on
`dev` first. This fork tracks `main`.

**Routine sync (merge upstream into the fork):**
```bash
git fetch upstream --tags
git log --oneline HEAD..upstream/main        # preview what's incoming
git merge upstream/main                       # or: git rebase upstream/main
# resolve conflicts — they'll be in whatever upstream-tracked files you customized
git push origin main
```

Prefer **merge** over rebase for the shared `main` unless you're certain no one
else pulled the fork. Check `git rev-list --left-right --count upstream/main...HEAD`
to see divergence at a glance (`0  0` = perfectly in sync, as it is now).

## Repo map

| Path | What it is |
|------|-----------|
| `skills/` | The core product — one dir per skill, each with `SKILL.md` (frontmatter `name` + `description` that drives auto-trigger). 14 skills; `using-superpowers` is the bootstrap entrypoint. |
| `hooks/` | `hooks.json` wires a `SessionStart` (startup/clear/compact) hook → `run-hook.cmd session-start`, which injects the `using-superpowers` bootstrap. `session-start-codex` is the Codex variant. |
| `.claude-plugin/` | Claude Code manifest (`plugin.json`) + dev `marketplace.json`. |
| `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `.opencode/`, `.pi/`, `.agents/`, `gemini-extension.json` | Per-harness plugin manifests/adapters. `.codex-plugin` is synced out via `scripts/sync-to-codex-plugin.sh`. |
| `tests/` | Shell + harness integration tests, one subdir per harness (`claude-code/`, `codex/`, `kimi/`, `opencode/`, `pi/`, `hooks/`, `shell-lint/`, …). Run via each dir's `run-*.sh`. |
| `scripts/` | `bump-version.sh` (version across all manifests per `.version-bump.json`), `lint-shell.sh`, `sync-to-codex-plugin.sh`. |
| `docs/` | Harness porting/install docs + `docs/superpowers/{plans,specs}` design history. |
| `evals/` | Skill-behavior eval harness (`superpowers-evals`), **gitignored** — cloned in separately, not part of the plugin. |
| `.github/` | `PULL_REQUEST_TEMPLATE.md` (strict — see upstream `CLAUDE.md`), issue templates. |

## Testing & validation

No `npm test`. Tests are shell scripts, run per-area:
```bash
tests/claude-code/run-skill-tests.sh          # Claude Code skill/integration tests
tests/hooks/test-session-start.sh             # bootstrap hook
tests/codex-plugin-sync/test-sync-to-codex-plugin.sh
scripts/lint-shell.sh                         # shellcheck baseline
```
`.pre-commit-config.yaml` only lints the `evals/` Python (ruff + ty) — it does
not gate plugin changes.

## Working conventions here

- **Version bumps** touch many manifests at once — always use
  `scripts/bump-version.sh`, never hand-edit versions (see `.version-bump.json`
  for the file list).
- **Changing a skill is changing behavior, not prose.** Upstream's bar is high
  (eval evidence, adversarial testing). For fork-local skill tweaks, still use
  the `writing-skills` skill and sanity-test the change before relying on it.
- **Codex plugin** content is generated/synced — don't hand-edit `.codex-plugin`
  as the source of truth; drive it from the skills + sync script.
- Follow my global `~/CLAUDE.md` for commit style (no `Co-Authored-By`, commit
  completed work to the current branch without asking).

## Contributing back to upstream (rare)

If a change is genuinely general-purpose and worth upstreaming, it follows
upstream's rules, **not** these: read the tracked `CLAUDE.md` and
`.github/PULL_REQUEST_TEMPLATE.md` in full, target the **`dev`** branch, fill
every template section, disclose the agent/harness, and get a human review of
the full diff. Upstream has a ~94% PR rejection rate — most fork customizations
should simply *stay in the fork*.
