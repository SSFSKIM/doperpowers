# to-human

The `to-human` output style (`output-styles/to-human.md`) assumes a human who
reads a report stream, not the transcript: the model wraps what they should
read in `<to-human>`, what is essential in `<essential>`, what it needs from
them in `<need-input>`, and leaves its working record unwrapped. The design in
`docs/doperpowers/specs/2026-09-05-sminos-human-stream-design.md` left the
consumer of those marks to a separate GUI. This mod makes the Claude Code
terminal that consumer.

It is a plugin of function hooks (a "mod"), so it loads only where
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set.

## What it draws

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
is drawn through the same hooks, so it folds too; `[ full transcript ]` is
the way to see everything.

## Running it

```
claude --plugin-dir mods/to-human --debug
```

`--plugin-dir` watches the folder, so a saved edit reloads the module. A tree
the engine refuses draws the engine's own component instead and the reason is
in the debug log under `ui.render (<Component>)`.

```
claude plugin validate mods/to-human   # what the module hooks and calls
claude plugin test mods/to-human       # tests/
npx -p typescript@5 tsc -p mods/to-human/tsconfig.json
```

Typechecking reads `.claude/types/claude-code.d.ts`, which `/plugin-types`
writes (gitignored); regenerate it after a Claude Code update.

## Known limits

- A marked span's body draws as plain text: bold, bullets and code fences show
  their markdown source. The unfolded view is the engine's markdown drawing.
- A literal mention of a tag in prose (`` `<to-human>` `` in a sentence about
  the tags) parses as a span.
- Unfold state lives in the module and resets on reload or a new session.
