# Doperpowers — Contributor Guidelines

`doperpowers` is a personal fork of `obra/superpowers` — a multi-harness plugin
(mostly *skills*) that gives coding agents a full software-development
methodology (brainstorm → worktree → plan → subagent-driven TDD → review →
finish). Skills load from `skills/` and are invoked via the `Skill` tool.

The fork is for personal use. Staying in sync with upstream is **not** a goal,
so tracked upstream files may be edited directly — do not contort a design into
fork-only indirection for merge-safety.

## "Compliance" changes to skills

Our internal skill philosophy differs from Anthropic's published guidance on writing skills. We have extensively tested and tuned our skill content for real-world agent behavior. Changes that restructure, reword, or reformat skills to "comply" with Anthropic's skills documentation will not be accepted without extensive eval evidence showing the change improves outcomes. The bar for modifying behavior-shaping content is very high.

## Bulk or spray-and-pray PRs

Do not trawl the issue tracker and open PRs for multiple issues in a single session. Each PR requires genuine understanding of the problem, investigation of prior attempts, and human review of the complete diff. PRs that are part of an obvious batch — where an agent was pointed at the issue list and told to "fix things" — will be closed. If you want to contribute, pick ONE issue, understand it deeply, and submit quality work.

## Golden Rule: Simplicity-First Protocols

No restriction or process enforcement beyond what is necessary. Agents are
not dumb — they carry their own situational judgment, and every constraint
that substitutes for that judgment makes the worker dumber than the model
running it. When authoring or editing skills and worker protocols, pursue
the fewest hard gates and the least strict DO / DO-NOT language: a hard
constraint earns its place only when the action it bans (or mandates) is
truly validated — it maps to a definite failure state, observed or
structural, not a hypothetical one. Everything else is stated as ownership
and outcomes; the worker chooses its means.

## Skill Changes Require Evaluation

Skills are not prose — they are code that shapes agent behavior. If you modify skill content:

- Use `doperpowers:writing-skills` to develop and test changes
- Run pressure testing appropriate to the skill's consumers and failure modes
- Show before/after eval results in your PR
- Follow the essentialist principle: a skill carries only what the reading model cannot derive itself — validated knowledge, interfaces, defaults with their reasons — and leaves room for situational judgment. Adding constraint or enforcement machinery needs eval evidence of the failure it prevents.
- "Your human partner" language is deliberate — don't rewrite the project's voice.

## Eval harness

Skill-behavior evals live in [superpowers-evals](https://github.com/prime-radiant-inc/superpowers-evals/), cloned into `evals/` — see `evals/README.md` for setup. The harness drives real tmux sessions of Claude Code / Codex and judges skill compliance with an LLM verifier. Plugin-infrastructure tests still live at `tests/`.

## Understand the Project Before Contributing

Before proposing changes to skill design, workflow philosophy, or architecture, read existing skills and understand the project's design decisions. Doperpowers has its own tested philosophy about skill design, agent behavior shaping, and terminology (e.g., "your human partner" is deliberate, not interchangeable with "the user"). Changes that rewrite the project's voice or restructure its approach without understanding why it exists will be rejected.

## Upstream: cherry-pick, never merge

```
origin    → https://github.com/SSFSKIM/doperpowers.git   (this fork)
upstream  → https://github.com/obra/superpowers.git      (the source project)
```

Upstream is reviewed commit-by-commit and cherry-picked. **Never merge or rebase
`upstream/main` into this fork.** The fork has diverged by hundreds of commits,
and most upstream skill edits now *regress* fork content rather than improve it —
a bulk merge would silently undo work that was declined on the merits.

```bash
git fetch upstream --tags
git log --oneline HEAD..upstream/main                    # what's outstanding
git rev-list --left-right --count upstream/main...HEAD   # behind / ahead
git diff $(git merge-base upstream/main HEAD) HEAD -- <path>   # has the fork touched this file?
```

Triage each candidate commit: files still byte-identical to the merge base can be
taken wholesale; files the fork rewrote need a re-graft or a decline. Rebrand on
import (`superpowers:` → `doperpowers:`, `.superpowers/` → `.doperpowers/`,
`docs/superpowers/` → `docs/doperpowers/`) and grep for residual `superpowers`
afterward. Commits touching mechanisms this fork removed — `hooks/`, the Gemini
CLI adapter, Codex portal packaging — are automatically irrelevant.

## Repo map

| Path | What it is |
|------|-----------|
| `skills/` | The core product — one dir per skill, each with `SKILL.md` (frontmatter `name` + `description` that drives auto-trigger). 14 skills; `using-doperpowers` is the bootstrap entrypoint. |
| ~~`hooks/`~~ | **Removed.** The `SessionStart` bootstrap (which injected the `using-doperpowers` skill index to shape auto-triggering) was torn out across all harnesses; the `using-doperpowers` skill itself was already deleted upstream-side in this fork, leaving the hook injecting an error. Skills still load from `skills/`; they just no longer get the bootstrap's trigger guidance. |
| `.claude-plugin/` | Claude Code manifest (`plugin.json`) + dev `marketplace.json`. |
| `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `.opencode/`, `.pi/`, `.agents/`, `gemini-extension.json` | Per-harness plugin manifests/adapters. `.codex-plugin` is a local manifest only (the external fork sync was retired in v7.23.0; script recoverable from git history). |
| `tests/` | Shell + harness integration tests, one subdir per harness (`claude-code/`, `codex/`, `shell-lint/`, …). Run via each dir's `run-*.sh`. (Note: `opencode/`, `kimi/`, `pi/`, `antigravity/` test harnesses whose plugin dirs were already pruned — orphaned, not wired to any runner.) |
| `scripts/` | `bump-version.sh` (version across all manifests per `.version-bump.json`), `lint-shell.sh`. |
| `docs/` | Harness porting/install docs + `docs/doperpowers/{plans,specs}` design history. |
| `evals/` | Skill-behavior eval harness (`superpowers-evals`), **gitignored** — cloned in separately, not part of the plugin. |
| `.github/` | `PULL_REQUEST_TEMPLATE.md` (strict — see upstream `CLAUDE.md`), issue templates. |

## Testing & validation

No `npm test`. Tests are shell scripts, run per-area:
```bash
tests/claude-code/run-skill-tests.sh          # Claude Code skill/integration tests
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
