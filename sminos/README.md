# sminos

The project family as a Claude Code plugin: every session working in a
project is a member that sees the others, messages them and its human, hands
work between them, and spans machines through a git mirror or a desk hub.
The plugin carries the `sminos` CLI and skill, the shell hooks that join a
session to its project and record what it sent its human, and the function
hooks (mods) that make a session reachable from outside it: the bridge, the
async question tool `mcp__sminos__AskUserQuestion`, and the session's
`Sminos-Session` address in commits and PRs. It stands alone: nothing of
doperpowers' is needed for it to run.

## Install

From the doperpowers marketplace:

```text
/plugin marketplace add SSFSKIM/doperpowers
/plugin install sminos@doperpowers
```

Its hooks must sit outside every other plugin's but to-human's, so the bridge
sees a call's input as the model wrote it and its result after any secrets
guard scrubbed it. A dependency cannot place it there; the settings' order
does. In `~/.claude/settings.json` (a host's managed settings carry the same
list):

```json
"prependPlugins": ["to-human@doperpowers", "sminos@doperpowers", "doperpowers@doperpowers"]
```

The mods load only where `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set.

## Where things are

- [`skills/sminos/SKILL.md`](skills/sminos/SKILL.md) — what a member does:
  find, message and reach the other sessions, spawn and retire them.
- [`skills/sminos/references/setup.md`](skills/sminos/references/setup.md) —
  a machine's one-time work: a project and its mirror, enrollment at the desk
  hub, the daemon, the policy.
- [`hooks/mods/README.md`](hooks/mods/README.md) — the bridge, the ask and the
  address, and the contract other plugins read
  ([`types/sminos.d.ts`](types/sminos.d.ts)).
- `tests/run-sminos-tests.sh` (the CLI and shell hooks) and
  `tests/mods/run.sh` (the mods).
