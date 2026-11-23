# Doperpowers agents for Codex

These TOML definitions port the review roles in `agents/*.md` to Codex's native
subagent runtime. Their names remain `doperpowers:<role>`. Claude continues
loading the Markdown definitions; its configuration is unchanged. The executors
(`plan-executor`, `task-executor`) have no port: a spec is executed in Claude
Code.

| Role | Model | Effort |
|---|---|---|
| reviewer-low | gpt-5.6-sol | high |
| reviewer-medium | gpt-5.6-sol | xhigh |
| reviewer-high | gpt-6-astra | high |
| adversarial-reviewer | gpt-6-astra | high |
| critique | gpt-6-astra | high |
| task-reviewer | gpt-5.6-sol | xhigh |

The reviewer pins match Claude's GPT routes. The critic uses Astra for design
judgment. Role files pin both model and effort, so changing the parent model
does not change them.

## Install or update

Codex discovers personal agents in `~/.codex/agents/`. The plugin manifest
does not install these files. From this repository's root, copy them there:

```sh
mkdir -p "$HOME/.codex/agents"
rm -f "$HOME/.codex/agents"/doperpowers-*.toml
for agent in codex/agents/*.toml; do
  cp "$agent" "$HOME/.codex/agents/doperpowers-$(basename "$agent")"
done
```

Repeat the copy after updating the definitions; the `rm` clears copies of roles
since removed. For a project-only installation, use that project's
`.codex/agents/` instead. Start a new Codex task to discover
the installed roles.

## Routing

Reviews run through native dispatch: `agent_type =
"doperpowers:reviewer-low"`, `reviewer-medium`, or `reviewer-high`, using the full `doperpowers:` prefix for each. Specs and plans
use `doperpowers:adversarial-reviewer`; design debates use `doperpowers:critique`.
A milestone's review uses `doperpowers:task-reviewer`.

When a shared skill says `Agent`, use Codex's native spawn operation with the
declared role and a fresh context. `SendMessage` means the native message or
follow-up operation; wait for completion before treating a result as a review.
Reviewer definitions carry a no-delegation boundary
as instructions: Claude's `disallowedTools` field is not a Codex agent setting.
These definitions do not establish a separate permission boundary; the parent
session's permissions still matter.

This port registers roles, not Claude's `Workflow` tool. For a panel, the Codex
controller orchestrates native agents using the stages and result contract in
`skills/review-code/references/panel.md`, respecting the available concurrency.
It does not execute the Claude workflow script.

## Verify

```sh
python3 tests/codex/test-native-agents.py
codex debug prompt-input 'Review this branch with a native doperpowers reviewer.'
```

The first check verifies the port against the original contracts and model pins.
The prompt diagnostic verifies instruction routing and the disabled skill catalog;
an actual native spawn verifies runtime discovery. Agent configuration follows
[Codex custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents).
