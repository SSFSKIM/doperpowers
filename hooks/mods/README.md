# mods

Function hooks of the doperpowers plugin: one module (`register.tsx`, named
by `hooks/hooks.json` under `modules`) that registers each mod below. The
engine loads it only where `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set and
ignores it elsewhere; the shell hooks beside this folder run everywhere.

## to-human (`to-human.tsx`)

The `to-human` output style (`output-styles/to-human.md`) assumes a human who
reads a report stream, not the transcript: the model wraps what they should
read in `<to-human>`, what is essential in `<essential>`, what it needs from
them in `<need-input>`, and leaves its working record unwrapped. This mod
makes the Claude Code terminal the consumer of those marks.

Nothing changes until the first assistant message of the session that carries
a mark, so a session without the output style is left alone. From then on:

- An assistant message draws only its marked spans, each under a colored
  label: `to human` in cyan, `essential` in yellow, `need input` in magenta. A
  span still streaming shows `…` after its label. A message with an unmarked
  working record beside its spans gets a dim `[ working record ]` button that
  unfolds the engine's own drawing of the whole block (markdown intact); a
  message with no marks at all is one dim row with that button.
- Tool rows (`ToolUse`, `ToolResult`, the folded `ToolGroup` count line) draw
  nothing.
- The band above the prompt shows `to-human view · [ full transcript ]`, which
  switches the whole transcript to the engine's drawing; the same button then
  reads `[ report only ]`.

The stored messages are untouched: the transcript on disk carries the tags as
written, and the model reads what it wrote. The `ctrl+o` detailed transcript
is drawn through the same hooks, so it folds too.

Known limits: a marked span's body draws as plain text (bold, bullets and
code fences show their markdown source; the unfolded view is the engine's
markdown drawing); a literal mention of a tag in prose parses as a span;
unfold state lives in the module and resets on reload or a new session.

## kairos (`kairos.tsx`)

A switch for the `kairos` proactive mode in the prompt footer, where the
engine draws its mode labels (`focus`, `memory paused`): `[ kairos off ]`
dim at rest, `[ kairos on ]` while the session is in the mode. One click
runs `/kairos` or `/kairos off` as if the person typed it.

The mode is still the shell hooks': `/kairos` carries the skill body into
the turn and `kairos-toggle.sh` records the session id under
`~/.claude/kairos`; `kairos.sh` re-injects the body after every compaction
and on resume. This module never writes that state. It reads it once at
session start (`KAIROS=1`, or the flag file for this session id) to draw the
button, watches `command.run` to flip the label when the command runs from
any source, and on a press calls `$.command.run` with the command the label
implies. A press while a turn runs is queued until the session is idle, as a
typed command would be. (`$.prompt.submit` refuses text beginning with `/`;
a slash command from a plugin goes through `command.run`.)

Known limits: switching on starts a turn, as typing `/kairos` does, and so
does switching off; a fork gets a new session id and starts out of the mode,
so the button reads `off` there, as the shell hooks do.

## Developing

```
claude --plugin-dir . --debug            # the repo as the plugin, hot reload on save
claude plugin validate .                 # what the module hooks and calls
claude plugin test tests/mods            # the mods' tests
npx -p typescript@5 tsc -p hooks/mods/tsconfig.json
```

Typechecking reads `.claude/types/claude-code.d.ts` at the repo root, which
`/plugin-types` writes (gitignored); regenerate it after a Claude Code update.
A tree the engine refuses draws the engine's own component instead and the
reason is in the debug log under `ui.render (<Component>)`.
