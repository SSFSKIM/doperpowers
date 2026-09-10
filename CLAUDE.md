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
afterward. Commits touching mechanisms this fork removed — the `hooks/` bootstrap, the Gemini
CLI adapter, Codex portal packaging — are automatically irrelevant.

## Repo map

| Path | What it is |
|------|-----------|
| `agents/` | Registered agents, addressed as `doperpowers:<name>`: `critique` (design critic, debated over SendMessage); `reviewer-low` / `reviewer-medium` / `reviewer-high` (one rubric body, pinned to sol/high, sol/xhigh, astra/high through the local gateway — the single-reviewer rungs of `review-code`, dispatchable from any session or subagent) and `adversarial-reviewer` (its spec/plan challenge reviewer); `plan-executor` (opus/high) executes a pinned plan for the session that authored it — SDE controller for a task-decomposed plan, sequential for an ExecPlan; dispatched by the board Architect past its build edge, and by writing-plans in an interactive session (execplan's own Step 3 stays inline — an ExecPlan is one agent's sequential work). The panel workflow reaches the reviewers by `agentType`, overriding model and effort per rung. |
| `skills/` | The core product — one dir per skill, each with `SKILL.md` (frontmatter `name` + `description` that drives auto-trigger). 18 skills. Worker protocols for the board loop (architect / implement / spike) are plain files under `issue-tracker/references/`, deliberately not skills — nothing invokes them by name; the dispatcher pins their path into the spawn bootstrap. |
| `application-agents/` | Deployed agent applications that are not skills — nothing invokes them by name from a session. `triaging-feedback/`: the feedback→triage poller (TypeScript, its own `npm test`), its worker protocol, and setup docs; the worker-host under `infra/` runs it. |
| `hooks/` | The `kairos` proactive mode: `kairos.sh` on `SessionStart` injects the `kairos` skill's body at startup and after every compaction for a session in the mode — launched with `KAIROS=1`, or switched on mid-session by typing `/kairos`, which `kairos-toggle.sh` (on `UserPromptExpansion`) records as a flag file under `~/.claude/kairos/<session-id>`; `/kairos off` removes it. Every other session gets nothing. `experimental-context.sh` / `experimental-context-toggle.sh` are the same shape for the experimental `/experimental-context` mode: the session writes keyed `<revisit key="…">` entries in its messages, and after every compaction and on resume the hook re-injects the skill body plus the latest value per key read from the transcript (`transcript_path` is on every hook payload), so governing intent survives repeated compaction verbatim instead of decaying through summaries of summaries. The upstream `SessionStart` bootstrap that used to live here (injecting the `using-doperpowers` skill index) was torn out; skills load from `skills/` directly. |
| `output-styles/` | Output styles the harness auto-loads from the plugin. `to-human.md`: for sessions whose human reads a report stream (`<to-human>`, `<essential>`, `<need-input>`) instead of the transcript (selected per launch via `outputStyle`; design in `docs/doperpowers/specs/2026-09-05-sminos-human-stream-design.md`). |
| `.claude-plugin/` | Claude Code manifest (`plugin.json`) + dev `marketplace.json`. |
| `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `.opencode/`, `.pi/`, `.agents/`, `gemini-extension.json` | Per-harness plugin manifests/adapters. `.codex-plugin` is a local manifest only (the external fork sync was retired in v7.23.0; script recoverable from git history). |
| `tests/` | Shell + harness integration tests, one subdir per harness (`claude-code/`, `codex/`, `shell-lint/`, …). Run via each dir's `run-*.sh`. (Note: `opencode/`, `kimi/`, `pi/`, `antigravity/` test harnesses whose plugin dirs were already pruned — orphaned, not wired to any runner.) |
| `scripts/` | `bump-version.sh` (version across all manifests per `.version-bump.json`), `lint-shell.sh`. |
| `archive/` | Retired skills kept for reference, not loaded by any harness (`domain-modeling/`: the CONTEXT.md glossary and ADR convention). |
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
  for the file list). Bump in the same commit as the change: the plugin
  marketplace updates by version number alone, so a feature merged under a
  number the cache already holds reports "already at the latest version" and
  never installs (kairos, 2026-09-06).
- **Plugin hook matchers see qualified names.** The harness expands a plugin
  skill's slash command as `doperpowers:<skill>` (observed in a
  `UserPromptExpansion` payload: `command_name: "doperpowers:kairos"`), and a
  matcher is a whole-string match — write `doperpowers:<skill>|<skill>`, not
  `<skill>`. Not in the harness docs.
- **Changing a skill is changing behavior, not prose.** Upstream's bar is high
  (eval evidence, adversarial testing). For fork-local skill tweaks, still use
  the `writing-skills` skill and sanity-test the change before relying on it.
