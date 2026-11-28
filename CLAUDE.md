# Doperpowers

`doperpowers` is a personal fork of `obra/superpowers` — a multi-harness plugin
(mostly *skills*) that gives coding agents a full software-development
methodology (brainstorm → worktree → plan → subagent-driven TDD → review →
finish), and the marketplace of four sibling plugins beside it.

The fork is for personal use. Staying in sync with upstream is **not** a goal,
so tracked upstream files may be edited directly — do not contort a design into
fork-only indirection for merge-safety.

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

## Changing agent-facing text

Skills, agent definitions, protocols and prompts shape agent behavior: a
wording change moves what agents do. They carry only what the reading model
cannot derive itself — validated knowledge, interfaces, defaults with their
reasons — and a kept rule states its reason. A change is tested by its stakes:
cutting duplicate, derivable, dead or wrong text ships on review alone;
removing or weakening a rule with an incident or an eval behind it needs a
control-versus-variant run on today's models first (Fable and Opus, 5 runs
each), and where that costs more than the change is worth, the rule stays,
restated with its reason. A new constraint comes with evidence of the failure
it prevents. `doperpowers:writing-skills` holds the doctrine and ways to test.
"Your human partner" is the project's voice; keep it.

## Upstream: cherry-pick, never merge

Upstream is `obra/superpowers` (remote `upstream`). Take its commits one by
one; never merge or rebase `upstream/main` into this fork: it has diverged by
hundreds of commits, most upstream skill edits now regress fork content, and a
bulk merge would silently undo work declined on the merits. Triage, rebrand and
commands: `docs/upstream-sync.md`.

## The board

The board is this repository's GitHub issues, a backlog: the human names
tickets to work, and a session may take one that is ready to implement on its
own initiative. A ticket changes nothing about how its work is designed, built
or reviewed. Its automatic dispatch is dormant since 2026-10-18 (the owner's
ruling, `docs/doperpowers/specs/2026-10-18-board-dispatch-dormant.md`): the
sweep, the dispatchers, the worker protocols and the review stand-in stay in
the tree, tested and armed nowhere, and nothing in them describes how work
runs today. A `board #<n>` (or `board ticket <n>`, `dp#<n>`) in older code,
docs and commits names a ticket of the retired board service, mapped to its
issue in `docs/doperpowers/board-service-tickets.md`.

## Repo map

A part's detail is in the `CLAUDE.md` nearest its code.

| Path | What it is |
|------|-----------|
| `skills/` | The core product: one dir per skill, each with its `SKILL.md`. `issue-tracker`'s dispatch doctrine is the dormant board machinery. |
| `agents/` | Registered agents (`doperpowers:<name>`), each definition its own contract and model pin. No `CLAUDE.md` here: every `.md` in `agents/` registers as an agent. |
| `hooks/` | The plugin's shell hooks and, under `mods/`, its function hooks (compact and appeal tools, kairos button, plugin reload, interim filter). |
| `bin/` | On every session's Bash PATH: `query-transcript`, which runs its skill's program. |
| `output-styles/` | Styles the harness loads from the plugin (no `CLAUDE.md` here: every `.md` loads as a style). `to-human.md`'s `maws-to-human-contract: 6` is the message-tool shape MAWS parses; 7 is MAWS's own. |
| `.claude-plugin/` | Manifest and dev marketplace. `workflows` registers review-code's workflow as `doperpowers:code-review`; callers pass that name, since the Workflow tool refuses a `scriptPath` into the plugin cache. |
| `.codex-plugin/`, `.agents/` | Codex: the local plugin manifest and its dev marketplace. |
| `codex/agents/` | Codex ports (TOML) of the review roles, installed into `~/.codex/agents/` by hand; outside `agents/` because every `.md` there registers. `tests/codex/test-native-agents.py` holds each port to its source. |
| `devcloud/`, `to-human/`, `sminos/`, `web/` | The sibling plugins, each versioned on its own: devcloud (opt-in: the secrets guard, the Linux host image, the `devenv` and `vm` skills), to-human (the report view and the message tool), sminos (standalone: the project family, its CLI and daemon, the bridge, the ask tool), web (the fetch tool and its clipper). |
| `application-agents/` | Deployed agent applications that are not skills. |
| `infra/` | Hosts of the dormant board machinery (`worker-host/`, the `board-sweep` plist); none runs. |
| `devenv/` | This repository's own development environment, for devcloud hosts and the Macs. |
| `tests/`, `scripts/` | Per-area tests and runners; `bump-version.sh`, `lint-shell.sh`, `check-claudemd-budget.py`. |
| `archive/` | Retired skills and agents, loaded by no harness. |
| `docs/` | Install guide, `whats-inside.md` (the catalog of every skill, agent and hook), porting and upstream notes, `docs/doperpowers/{plans,specs}` design history. |
| `teaching/` | The owner's study course on the cloud-scale reference architecture. |
| `evals/` | Gitignored: where the `superpowers-evals` harness is cloned when wanted. |

## Testing & validation

CI is ci-kit: `.github/ci-kit.yml` defines the gates, which run on GitHub
Actions; `ci-gate` verifies a commit. No gate calls a live model; those tests
(the rest of `tests/claude-code/run-skill-tests.sh`'s list, the `live-*`
checks) run by hand. Per-area runners are `tests/<area>/run-*.sh`; there is
no `npm test`. Skill-behavior evals:
[superpowers-evals](https://github.com/prime-radiant-inc/superpowers-evals/)
drives real tmux sessions and judges skill compliance with an LLM verifier;
it is present only once cloned into `evals/` (setup in its README), and
`.pre-commit-config.yaml` lints only its Python.

## Working conventions here

- **Version bumps.** Bump a plugin's version in the same commit as its change,
  with `scripts/bump-version.sh` (`--plugin devcloud|to-human|sminos|web` for
  the others), never by hand: one version lives in several manifests
  (`.version-bump.json`). The marketplace installs by version number alone,
  so a change under a number the cache already holds never reaches a session.
  `--since origin/main` checks a change before it is pushed; the
  `version-bump` gate checks a PR. A path that never reaches a session belongs
  in its plugin's `unshipped` list.
- **Plugin hook matchers see qualified names.** The harness expands a plugin
  skill's slash command as `doperpowers:<skill>` (`command_name:
  "doperpowers:kairos"` in a `UserPromptExpansion` payload), and a matcher is
  a whole-string match: write `doperpowers:<skill>|<skill>`. Not in the
  harness docs.
- **Hook order** is the owner's `prependPlugins` (`~/.claude/settings.json`,
  a host's managed settings likewise: `to-human@doperpowers`,
  `sminos@doperpowers`, `doperpowers@doperpowers`, outermost first), which
  seats those three outside every user-tier plugin; no dependency can.
- **Agent definitions.** The pins of `plan-executor`, `task-executor`
  (opus/high) and `task-reviewer` (sol/xhigh) change only on an explicit
  instruction, whatever model wrote the spec: the frontier's work is the design
  and the spec; running the plan is close-frontier work. The executors cannot
  ask the human: what needs the human comes back up the dispatch chain for the
  main session to ask and relay. The engine hands every subagent every MCP
  tool, so every definition withholds the session-only ones
  (`mcp__doperpowers__compact`, `mcp__sminos__AskUserQuestion`,
  `mcp__to-human__message`) through `disallowedTools`; the reviewers and
  `adversarial-reviewer` block `Agent` and `Skill` too, so a review cannot
  start one inside itself. `autoCompactWindow` compacts 33k below its value.
- **The public face follows the tree.** `README.md` and `docs/whats-inside.md`
  are what a visitor reads; a skill, agent or hook added, retired or made
  manual changes its row in `whats-inside.md` in the same change.
- **CLAUDE.md files hold what the code cannot tell.** Each is read whole by
  every session and subagent touching its directory, so it holds what a
  session needs before reading the code and cannot get from it: what is there
  and where, invariants and traps with a clause of reason each, commands that
  are not discoverable, conventions binding work there. How a feature works
  belongs in its code and docstrings, why in its spec, how it came to be and
  what was measured in git. A root map row stays a sentence or two; only a rule
  binding work anywhere belongs in the root. Before cutting a passage, move a
  fact whose only copy it is to where it belongs. Each file stays under 1,500
  words (the `claudemd-budget` gate). No `CLAUDE.md` where a loader reads
  every `.md` (`agents/`, `output-styles/`, a `commands/` directory).
