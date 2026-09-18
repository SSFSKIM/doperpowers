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
  span's body is the engine's own markdown drawing of the span's text (the
  block is handed back beneath the hook with that text in place of the
  whole), so a table or a list inside a mark draws as it would unmarked. A
  span still streaming shows `…` after its label. A message with an unmarked
  working record beside its spans gets a dim `[ working record ]` button that
  unfolds the engine's drawing of the whole block.
- Messages with no marks at all, and tool calls with their results, are
  working record, and a run of it draws one `[ working record ]` button
  rather than one button per row: the run breaks at a prompt, at a message
  that carries marks, or at a question the human answered, so what stands
  between two things they read opens and closes as a unit. The button is
  drawn by the row the run starts at and the rest of the run draw nothing;
  unfolded, the run shows the engine's own rows (a group of reads the engine
  would fold into a count line shows each call) under `[ fold to report ]` at
  the top of the run, where it stays as the run grows.
- A question answered through `AskUserQuestion` draws as the engine draws it
  (the question and the answer given) in the report itself: the answer is the
  human's own words, and they read it as they read a mark.
- The band above the prompt shows `to-human view · [ full transcript ]`, which
  switches the whole transcript to the engine's drawing; the same button then
  reads `[ report only ]`.

While a message streams, none of this is drawn yet: the engine mounts an
`AssistantMessage` only once the block is whole, so a hook of that component
cannot restyle text as it arrives. The shell hook beside this folder,
`../to-human-stream.sh` on `MessageDisplay`, covers that stretch — it is
handed each batch of newly completed lines and returns what to draw in its
place, so a mark becomes the same colored label and the working record dims
as the message arrives. The engine runs up to three of a message's flushes
at once and dispatches the last one the moment the message ends, so each
flush records its index when it is done and the next waits for that record
before reading which marks are open; without the wait, a short message's
tail was drawn before the flush that closed its mark had finished, and came
through undimmed. The hook's labels are what this module then reads: once
the hook has run, the block's text carries those headers instead of the
tags, and `parse` takes either form (the tags when the hook is not
installed, the headers when it is). The two views line up, so the message
settles into the fold without changing shape.

The stored messages are untouched by both: the transcript on disk carries the
tags as written, and the model reads what it wrote. The `ctrl+o` detailed
transcript is drawn through the same hooks, so it folds too.

Known limits: a literal mention of a tag in prose parses as a span; unfold
state lives in the module and resets on reload or a new session; a run's
rows are known by the order they first drew in, so a resumed session that
redraws history out of order can put a button on the wrong row until the
next redraw.

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
claude --plugin-dir . --debug                        # the repo as the plugin, hot reload on save
claude plugin validate .claude-plugin/plugin.json    # what the module hooks and calls
tests/mods/run-mods-tests.sh                         # the mods' tests
tests/claude-code/test-to-human-stream-hook.sh       # the streaming hook's tests
npx -p typescript@5 tsc -p hooks/mods/tsconfig.json
```

Typechecking reads `.claude/types/claude-code.d.ts` at the repo root, which
`/plugin-types` writes (gitignored); regenerate it after a Claude Code update.
A tree the engine refuses draws the engine's own component instead and the
reason is in the debug log under `ui.render (<Component>)`.
