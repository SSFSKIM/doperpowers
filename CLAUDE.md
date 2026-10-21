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

## The board: a backlog, its dispatch dormant

Since 2026-10-18 the board's automatic dispatch is dormant (the owner's
ruling, `docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md`).
The board holds the backlog: the human names tickets to work, and a
session may take a ticket that is ready to implement on its own
initiative; whoever takes one runs it through the attended workflow —
brainstorming / execspec, a plan-executor or subagents, review-code, the
merge. The sweep, the dispatchers, the worker protocols, the review
stand-in and `qa-loop` stay in the tree, tested and armed nowhere; nothing
in them describes how work runs today. If board-driven spawning returns,
it is expected to run that attended workflow on a trigger, not to re-arm
this doctrine as written.

## Repo map

Each row orients; a part's detail is in the `CLAUDE.md` nearest its code,
attached the first time a session reads a file beneath it.

| Path | What it is |
|------|-----------|
| `agents/` | Registered agents, addressed as `doperpowers:<name>`; each definition is its own contract, and the engine lists each with its description (no `CLAUDE.md` here: every `.md` in `agents/` registers as an agent). Pins: `reviewer-low` / `reviewer-medium` / `reviewer-high` sol/high, sol/xhigh, astra/high through the local gateway (the single-reviewer rungs of `review-code`; the panel workflow reaches them by `agentType`, overriding model and effort per rung); `plan-executor`, `task-executor` and `qa-loop` (dormant) opus/high; `task-reviewer` sol/xhigh. Every reviewer agent, and `adversarial-reviewer`, blocks `Agent` and `Skill` so a reviewer cannot route back into `review-code` and start a review inside its own. The three pins — plan-executor and task-executor opus/high, task-reviewer sol/xhigh — change only on an explicit instruction, by edit or by dispatch override, whatever model wrote the spec (usually the frontier one): the frontier's work is the design and the spec; running the plan and building its milestones is close-frontier work. Both executors run detached from the human (`AskUserQuestion` is disallowed in their definitions): what needs an input only the human or the work's owners can give is escalated up the dispatch chain until the main session puts it to the human and relays the answer down. Every definition withholds the mods' session-only tools (`mcp__doperpowers__compact`, `mcp__sminos__AskUserQuestion`, `mcp__to-human__message`) through `disallowedTools`, since the engine hands every subagent every MCP tool; an `autoCompactWindow` compacts 33k below its value (plan-executor's 483000 at 450k, its state rebuilt from the spec, the ledger and git log). |
| `skills/` | The core product — one dir per skill, each with `SKILL.md` (frontmatter `name` + `description` that drives auto-trigger). 14 skills. `brainstorming` closes and presents the design; `execspec` writes the living spec from the approved design, reviews it, and executes it (its `references/living-spec.md` is the document's doctrine, read by SDE, decomposing, and the board protocols). `issue-tracker` is the board as a backlog; its dispatch doctrine is dormant and stays in the tree, tested and armed nowhere (its SKILL.md lists it under Dormant machinery). |
| `application-agents/` | Deployed agent applications that are not skills — nothing invokes them by name from a session. Detail in `application-agents/CLAUDE.md`. |
| `hooks/` | The doperpowers plugin's hooks: `kairos`, the `PreCompact` instructions, the `<message>` streaming hook, and under `mods/` the function hooks (kairos button, agents pane, compact tool, plugin reload, interim filter, auto-mode appeal). Detail in `hooks/CLAUDE.md` and `hooks/mods/CLAUDE.md`. |
| `devcloud/` | A second plugin in this marketplace, opt-in, versioned on its own: the secrets guard mod, the Linux host's image and boot program, and the `devenv` skill. Detail in `devcloud/CLAUDE.md`. |
| `to-human/` | A third plugin in this marketplace, versioned on its own: the report view of a session under the `to-human` output style, the message tool (`mcp__to-human__message`), and a notification for each message sent. Detail in `to-human/CLAUDE.md`. |
| `sminos/` | A fourth plugin in this marketplace, standalone, versioned on its own: the project family, its CLI, daemon and shell hooks, the bridge, the ask tool and the session's address. Detail in `sminos/CLAUDE.md` and beside each part's code. The plugins' hook order is the owner's `prependPlugins` (`~/.claude/settings.json`, a host's managed settings likewise: `to-human@doperpowers`, `sminos@doperpowers`, `doperpowers@doperpowers`, outermost first), which seats those three outside every user-tier plugin, devcloud's secrets guard and cua's among them; no dependency can. |
| `output-styles/` | Output styles the harness auto-loads from the plugin (no `CLAUDE.md` here: every `.md` loads as a style). `to-human.md`: for sessions whose human reads a report stream instead of the transcript (selected per launch via `outputStyle`; design in `docs/doperpowers/specs/2026-09-05-sminos-human-stream-design.md`); its front matter `maws-to-human-contract: 6` is the message-tool shape, 7 being MAWS's own. |
| `.claude-plugin/` | Claude Code manifest (`plugin.json`) + dev `marketplace.json`. The manifest's `workflows` key registers `skills/review-code/workflows/code-review.js` as the named workflow `doperpowers:code-review`: the Workflow tool's `scriptPath` passes the ordinary read-path check (the working directory and added directories only), so a path into the plugin cache is always refused — 56 such failures in this machine's transcripts, 2026-09-02 → 10-04, every one of them — and every caller passes the name. |
| `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `.opencode/`, `.pi/`, `.agents/`, `gemini-extension.json` | Per-harness plugin manifests/adapters. `.codex-plugin` is a local manifest only (the external fork sync was retired in v7.23.0; script recoverable from git history). |
| `codex/agents/` | The Codex ports of `agents/*.md`: native role definitions (TOML) with their install guide, copied into `~/.codex/agents/` by hand — no manifest installs them. They live outside `agents/` because Claude loads every `.md` under `agents/` as an agent, so the guide there was registered as a `doperpowers:codex:README` agent with every tool. `tests/codex/test-native-agents.py` holds each port to its source contract and model pin. |
| `tests/` | Shell + harness integration tests, one subdir per harness, run via each dir's `run-*.sh`; `tests/mods/` holds the mods' TypeScript tests and `typecheck.sh`, the `mods-types` gate. Detail in `tests/CLAUDE.md`. |
| `scripts/` | `bump-version.sh` (one plugin's version across its manifests per `.version-bump.json`, doperpowers by default, `--plugin devcloud`, `--plugin to-human` or `--plugin sminos` for the others; marketplace entries addressed by name; a version not above every declared file's current one is refused, since the marketplace updates by number alone), `lint-shell.sh`. |
| `archive/` | Retired skills kept for reference, not loaded by any harness; what each was, and where its surviving rules live, is in `archive/CLAUDE.md`. |
| `docs/` | Harness porting/install docs + `docs/doperpowers/{plans,specs}` design history. |
| `evals/` | Skill-behavior eval harness (`superpowers-evals`), **gitignored** — cloned in separately, not part of the plugin. |
| `.github/` | `PULL_REQUEST_TEMPLATE.md` (strict — see upstream `CLAUDE.md`), issue templates. |

## Testing & validation

No `npm test`. Tests are shell scripts, run per-area:
```bash
tests/claude-code/run-skill-tests.sh          # Claude Code skill/integration tests
scripts/lint-shell.sh                         # shellcheck baseline
tests/mods/typecheck.sh                       # tsc over every plugin's mods and tests (the mods-types gate)
```
`.pre-commit-config.yaml` only lints the `evals/` Python (ruff + ty) — it does
not gate plugin changes.

## Working conventions here

- **Version bumps** touch many manifests at once — always use
  `scripts/bump-version.sh`, never hand-edit versions (see `.version-bump.json`
  for each plugin's file list; `--plugin devcloud`, `--plugin to-human` and
  `--plugin sminos` bump those, which never move with doperpowers). Bump in the same commit as the change: the plugin
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
- **A map row orients; detail lives beside the code.** A root Repo map row
  stays a sentence or two: what the path is and where its detail lives. A
  feature's detail goes in the nested `CLAUDE.md` nearest its code, never
  appended to the root row; only a rule that binds work anywhere in the repo
  belongs in the root. No `CLAUDE.md` where a loader reads every `.md`
  (`agents/`, `output-styles/`, a `commands/` directory).
