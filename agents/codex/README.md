# Doperpowers agents for Codex

These TOML definitions port the contracts in `agents/*.md` to Codex's native
subagent runtime. Their names remain `doperpowers:<role>`. Claude continues
loading the Markdown definitions; its configuration is unchanged.

| Role | Model | Effort |
|---|---|---|
| reviewer-low | gpt-5.6-sol | high |
| reviewer-medium | gpt-5.6-sol | xhigh |
| reviewer-high | gpt-6-astra | high |
| adversarial-reviewer | gpt-6-astra | high |
| critique | gpt-6-astra | high |
| task-reviewer | gpt-5.6-sol | high |
| plan-executor | gpt-5.6-sol | xhigh |
| task-executor | gpt-5.6-sol | high |
| qa-loop | gpt-5.6-sol | high |

The reviewer pins match Claude's GPT routes. The critic uses Astra for design
judgment; the executors and the QA agent that runs the board's review loop use
Sol at the project's execution tiers. Role files
pin both model and effort, so changing the parent model does not change them.
Claude's `plan-executor` and `qa-loop` are pinned to opus (2026-09-25); the
Codex mirrors keep Sol, since Codex has no Claude route.

## Install or update

Codex discovers personal agents in `~/.codex/agents/`. The plugin manifest
does not install these files. From this repository's root, copy them there:

```sh
mkdir -p "$HOME/.codex/agents"
for agent in agents/codex/*.toml; do
  cp "$agent" "$HOME/.codex/agents/doperpowers-$(basename "$agent")"
done
```

Repeat the copy after updating the definitions. For a project-only installation,
use that project's `.codex/agents/` instead. Start a new Codex task to discover
the installed roles.

Disable the companion skill in `~/.codex/config.toml` (update an existing rule
for this name if present):

```toml
[[skills.config]]
name = "doperpowers:codex-companion"
enabled = false
```

The name selector survives plugin cache/version changes. It affects Codex only;
the companion files are still available to Claude and the benchmark baseline.

## Routing

Replace any Codex instruction that requires the companion runtime with native
dispatch: `agent_type = "doperpowers:reviewer-low"`, `reviewer-medium`, or
`reviewer-high`, using the full `doperpowers:` prefix for each. Specs and plans
use `doperpowers:adversarial-reviewer`; design debates use `doperpowers:critique`.
A spec's Plan of Work and its individual milestones use `plan-executor` and
`task-executor`, and the controller sends task reviews to `task-reviewer`.

When a shared skill says `Agent`, use Codex's native spawn operation with the
declared role and a fresh context. `SendMessage` means the native message or
follow-up operation; wait for completion before treating a result as a review.
The task executor keeps its self-review contract; its controller owns the
independent reviewer. Reviewer definitions carry that same no-delegation boundary
as instructions: Claude's `disallowedTools` field is not a Codex agent setting.
These definitions do not establish a separate permission boundary; the parent
session's permissions still matter.

This port registers roles, not Claude's `Workflow` tool. For a panel, the Codex
controller orchestrates native agents using the stages and result contract in
`skills/review-code/references/panel.md`, respecting the available concurrency.
It does not execute the Claude workflow script or launch the companion runtime.

## Verify

```sh
python3 tests/codex/test-native-agents.py
codex debug prompt-input 'Review this branch with a native doperpowers reviewer.'
```

The first check verifies the port against the original contracts and model pins.
The prompt diagnostic verifies instruction routing and the disabled skill catalog;
an actual native spawn verifies runtime discovery. Agent configuration follows
[Codex custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents).
