# kairos

A switch for the `kairos` proactive mode in the prompt footer, where the
engine draws its mode labels (`focus`, `memory paused`): `[ kairos off ]`
dim at rest, `[ kairos on ]` while the session is in the mode. One click
runs `/kairos` or `/kairos off` as if the person typed it.

It is a plugin of function hooks (a "mod"), so it loads only where
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set.

## How it works

The mode is still the doperpowers plugin's: `/kairos` carries the skill body
into the turn and `hooks/kairos-toggle.sh` records the session id under
`~/.claude/kairos`, and `hooks/kairos.sh` re-injects the body after every
compaction and on resume. This module never writes that state. It reads it
once at session start (`KAIROS=1`, or the flag file for this session id) to
draw the button, watches `command.run` to flip the label when the command
runs from any source, and on a press calls `$.command.run` with the command
the label implies. A press while a turn runs is queued until the session is
idle, as a typed command would be.

A submitted prompt that begins with `/` is refused by the engine
(`$.prompt.submit` is for text the model reads); running a slash command
from a plugin is `$.command.run`, which is why the press goes that way.

## Running it

```
claude --plugin-dir mods/kairos --debug
```

The doperpowers plugin must be installed too: the button runs its command.

```
claude plugin validate mods/kairos
claude plugin test mods/kairos
npx -p typescript@5 tsc -p mods/kairos/tsconfig.json
```

Typechecking reads `.claude/types/claude-code.d.ts`, which `/plugin-types`
writes (gitignored); regenerate it after a Claude Code update.

## Known limits

- Switching on starts a turn, as typing `/kairos` does: the model reads the
  skill body and takes its next step at once. Switching off starts one too.
- The mode label the engine would draw (`focus`, `memory paused`) is
  redrawn by this module ahead of the button, joined by ` & ` as the engine
  joins them.
- A fork gets a new session id and starts out of the mode; the button
  reads `off` there, as the shell hooks do.
