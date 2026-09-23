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
- Messages with no marks at all, tool calls with their results, and prompt
  rows that are deliveries rather than the person's words (a subagent's or
  another session's message, a background task's notification, a schedule
  firing) are working record, and a run of it draws one `[ working record ]`
  button rather than one button per row: the run breaks at the person's own
  prompt, at a message that carries marks, or at a question the human
  answered, so what stands between two things they read opens and closes as
  a unit. The button is
  drawn by the row the run starts at and the rest of the run draw nothing;
  unfolded, the run shows the engine's own rows as the transcript draws them
  (a group of reads keeps its count line: each call in its place would be
  the ctrl+o form, its whole output inline; where the engine expands the
  group itself, in the ctrl+o transcript and under `--verbose`, each call is
  a row of its own in the group's run), with `[ fold to report ]` under the
  row the run ends at, where the person is when they finish reading, so as
  the run grows the button moves down with it.
- The line that closes a turn (`Baked for 3s`, `Waiting for N background
  agents to finish`) draws only while the run of the row before it is
  unfolded; otherwise nothing. The attachment rows the engine draws on its
  own (`Found N new diagnostic issues`) are not a render component a hook
  can reach, and still draw.
- A question answered through `AskUserQuestion` draws as the engine draws it
  (the question and the answer given) in the report itself: the answer is the
  human's own words, and they read it as they read a mark.
- A `need-input` span is a question the human answers from the terminal. The
  options the model wrote as `<choice>…</choice>` lines (one of them
  `<choice recommended>`) draw as buttons under the question, `★` on the
  recommended one, with `[ reply… ]` last; a question with no options has
  `[ reply… ]` alone. A press writes the person's box: a choice as the whole
  answer, `reply` as its opening, both in the form `Answering "<the
  question's first line>": <answer>`, and Enter sends it as the person's own
  prompt. (Nothing here submits: a prompt a plugin submits enters under the
  plugin's name, framed as the plugin's message to the model and labelled so
  in the transcript, by an origin no hook may change.) Once a prompt in that
  form enters, the span reads `need input · answered: <answer>` and its
  buttons go; a resumed session reads its answers back from the transcript.
- Above the prompt, `to-human view · [ full transcript ]` switches the whole
  transcript to the engine's drawing; the same button then reads
  `[ report only ]`.

While a message streams, none of this is drawn yet: the engine mounts an
`AssistantMessage` only once the block is whole, so a hook of that component
cannot restyle text as it arrives. The shell hook beside this folder,
`../to-human-stream.sh` on `MessageDisplay`, covers that stretch — it is
handed each batch of newly completed lines and returns what to draw in its
place, so a mark becomes the same colored label, a choice a line under `◇`
(`◆` for the recommended one), and the working record dims as the message
arrives. The engine runs up to three of a message's flushes
at once and dispatches the last one the moment the message ends, so each
flush records its index when it is done and the next waits for that record
before reading which marks are open; without the wait, a short message's
tail was drawn before the flush that closed its mark had finished, and came
through undimmed. The hook's labels are what this module then reads: once
the hook has run, the block's text carries those headers and markers instead
of the tags, and `parse` takes either form (the tags when the hook is not
installed, the headers when it is). The two views line up, so the message
settles into the fold without changing shape.

The stored messages are untouched by both: the transcript on disk carries the
tags as written, and the model reads what it wrote. The `ctrl+o` detailed
transcript is drawn through the same hooks, so it folds too.

Known limits: a literal mention of a tag in prose parses as a span, and a
literal ◇ or ◆ followed by a space inside a need-input question or choice
reads as a choice marker once the streaming hook has drawn it; unfold state
lives in the module and resets on reload or a new session (answers do not:
they are read from the transcript); a question is known by its first line, so
two questions that open alike are answered together; a run's rows are known
by the order they first drew in, so a resumed session that redraws history
out of order can put a button on the wrong row until the next redraw.

## agents (`agents.tsx`)

A map of the session's subagents and a window onto any of them. From the
session's first subagent on, the footer's mode slot (the right end of the
status line, beside the kairos switch) carries a button,
`[ 1 running · 2 done ]`, that opens and closes the `agents` pane
(docked beside the transcript in the fullscreen layout from 110 columns,
else seated above the prompt). The hint line under the prompt is the
engine's own row of pills, so a tree there cannot reach its right edge; the
mode slot is right-aligned by the engine.

- The pane draws every agent the session has had as the tree it spawned in:
  each under the agent whose loop started it (`$.agent.list()` names that
  as `parentId`), siblings in spawn order, done ones dim. The engine drops a
  finished agent from its list thirty seconds after it ends; the tree keeps
  every agent it once listed. A row reads
  `● description  type · model  elapsed`: `●` running, `✓` completed, `✗`
  failed, `○` killed. The agent whose transcript the engine's own tasks list
  has on screen is marked `◀ in view`.
- A press on a row draws that agent's transcript beneath the tree, read from
  the file the engine writes for it (`<session transcript>/subagents/agent-<id>.jsonl`):
  the task it was given (three lines), what it said in full, each tool call
  in one line (`Bash(ls -la)`, `Read(path)`, `Agent(description)`), the first
  line of each result, and the notes the engine slips it. Thinking and
  attachments are left out; past 300 entries the oldest are counted, not
  drawn; a file over 4 MiB is reported, not read. Pressing the row again
  folds the transcript.
- While the pane is open a one-second timer re-reads the list and, when the
  shown transcript grew, the file, and redraws only on a change; the elapsed
  times refresh every thirty seconds while anything runs. Closing the pane
  stops the timers. While the pane does not hold the keyboard the transcript
  follows its tail; focus it (a click, ctrl+x tab) to scroll, Esc to let it
  follow again.
- The `subagents/` directory is taken from the classic `SessionStart` and
  `SubagentStart` payloads' `transcript_path`, never guessed, so a resumed
  session's earlier agents (read from the `.meta.json` the engine leaves
  beside each transcript, parent included) are in the tree too.

Known limits: the pane is read-only (`$.agent` has no kill or message); an
agent read from disk alone shows as completed with no elapsed time (the
engine rewrites its meta file as it ends, so the file times say nothing of
its span) and no model unless the meta file names one; a teammate's
transcript is not under `subagents/`, so its row reads `no transcript on
disk`; a shown transcript is re-read whole each time its file grew.

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
