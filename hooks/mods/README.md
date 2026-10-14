# mods

Function hooks of the doperpowers plugin: one module (`register.tsx`, named
by `hooks/hooks.json` under `modules`) that registers each mod below. The
engine loads it only where `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set and
ignores it elsewhere; the shell hooks beside this folder run everywhere.

## to-human (`to-human.tsx`)

The `to-human` output style (`output-styles/to-human.md`) assumes a human who
reads a report stream, not the transcript: the model sends them messages in
`<message>`, asks for what it needs from them through AskUserQuestion (the
ask mod's, `async` when it can work on while they decide), and leaves its
working record unwrapped. The old `<to-human>`, `<essential>`,
`<need-input>` and `<insight>` marks read as aliases of `<message>` (an old
question's `<choice>` lines stay in its text, with no buttons); tags in inline code or fenced blocks stay literal. This mod
makes the Claude Code terminal the consumer of those marks.

Under MAWS (`MAWS_NATIVE_TO_HUMAN` set), MAWS draws the report itself; this view passes every drawing hook through on non-terminal surfaces, and the streaming hook draws nothing.

Nothing changes until the first assistant message of the session that carries
a mark, so a session without the output style is left alone. From then on:

- An assistant message draws only its marked spans, each under the
  `message` label in Claude's orange.
  On the terminal a
  span's body is the engine's own markdown drawing of the span's text (the
  block is handed back beneath the hook with that text in place of the
  whole), so a table or a list inside a mark draws as it would unmarked. A
  remote surface (the desktop app, VS Code, mobile) draws the body as the
  surface's own `Markdown` element instead: a render answer carries one
  props, so of several blocks handed back only the first draws there — Claude
  Desktop portals its native row into the first engine node and draws nothing
  at the rest, which left every span after the first label-only
  (2026-10-03). A
  span still streaming shows `…` after its label. A message with an unmarked
  working record beside its spans gets a dim `[ working record ]` button that
  unfolds the engine's drawing of the whole block, and the run of working
  record after that message opens and closes with it: the message is where
  the run starts, so two things the person reads have one button between
  them, never the message's and the run's stacked.
- Messages with no marks at all, tool calls with their results, and prompt
  rows that are deliveries of the model's own business rather than the
  person's words (a background command's or a monitor's notification, a
  schedule firing) are working record, and a run of it draws one
  `[ working record ]` button rather than one button per row: the run breaks
  at the person's own prompt, at a message that carries marks (one with
  record beside its marks starts the run itself), and at every row of the
  next two bullets, so what stands between two things they read opens and
  closes as a unit. The button is drawn by the row the run starts at and the
  rest of the run draw nothing;
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
- A question asked through `AskUserQuestion`, or through the ask mod's
  `mcp__doperpowers__AskUserQuestion` (an open async ask with its
  `[ answer ]` included), draws as it would unfolded (the question and the
  answer given) in the report itself: the answer is the human's own words,
  and they read it as they read a mark.
- Agent spawns stay in the report as the engine draws them: an `Agent`
  call and a `Workflow` of agents. `SendMessage` calls, received messages
  from agents, teammates or other sessions, and agent-finish notifications
  are working record. Unfolding the run or the full transcript reveals them.
- Above the prompt, `to-human view · [ full transcript ]` switches the whole
  transcript to the engine's drawing; the same button then reads
  `[ report only ]`.

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
installed, the headers when it is), with old `to human`, `essential` and
`need input` headers read as messages too (an old `◇`/`◆` choice line stays
text). The two views line up, so the message
settles into the fold without changing shape.

The stored messages are untouched by both: the transcript on disk carries the
tags as written, and the model reads what it wrote. The `ctrl+o` detailed
transcript is drawn through the same hooks, so it folds too.

Known limits: a literal mention of a tag in prose parses as a span; unfold
state lives in the module and resets on reload or a new session; a run's rows are known
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

## compact (`compact.tsx`)

Two tools the model can call, registered at `session.start` under the
plugin's name: `mcp__doperpowers__context_usage` and
`mcp__doperpowers__compact`. The first answers the input tokens of the
last response over the window the engine compacts against (the `summary`
breakdown's `rawMaxTokens`: the compaction window where client data, a
setting or an experiment set one, as `/context` shows it under
"Auto-compact window", else the model's; estimated locally, no request
sent) and where the engine compacts on its own (that window less the 20k
output reserve and 13k headroom: 867k on the 900k window a 1M model gets
here, 167k on a 200k one), so the model asks only when it is deciding. The
second is the model compacting its own context at a checkpoint of its
choosing.

The engine compacts only between turns (`$.session.compact` is refused while
a turn runs), so the tool defers: its handler keeps the request
(`instructions`, what this checkpoint's summary should keep or drop beyond
the standard summary; `resume`, the prompt to receive after the reset) and
answers at once that the compaction runs when the turn ends, so the model
ends its turn. At the `turn.complete` of a main-conversation turn the model
answered (`reason: "answer"`) the module calls `$.session.compact` (the
`/compact` path, trigger `plugin`: one model call over the live conversation
with the summary request appended, so the model that chose to compact
writes the summary; the `PreCompact` shell hook's `compact-instructions.md`
merges in) and then submits `resume` through `$.prompt.submit`, whatever the
compaction's outcome (a `{ skip }` or a failure is toasted), so a session
nobody watches never stalls on a turn the model ended to be compacted. A
request left by a turn that ended otherwise (an interruption, an API error)
is dropped at the next `turn.start`, so a turn the person starts is not
compacted behind them. Nothing is aborted: background shells, monitors, MCP
servers and subagents run on through a compaction, and their notifications
arrive in the turn after. The tool's description carries the guidance
(the work's checkpoints decide, size only sets how small a checkpoint will
do, why a checkpoint is worth compacting at, the token bands, call it last
and alone, end the turn).

A subagent's call to `compact` is refused (its turn ends are not the main
conversation's), and so is one to `context_usage` (`$.session.usage` reads
the main conversation, so it would answer the parent's figures). A
headless (`-p` / SDK) session gets neither tool: the engine has no
compactor a plugin can call there yet. The session and turn events are
taken with a matcher (`isInteractive: true`, `reason: "answer"`) because
kairos and agents register them too, and the engine admits one unmatched
registration of an event per module.

The tools are MCP tools to the engine, which tool search defers (the
model sees the name alone until it loads the tool with `ToolSearch`), so
the guidance in `compact`'s description would reach the model only once it
had already thought of compacting. A `tool.describe` hook on each tool
answers `isDeferred: false`, which the engine takes over its own placement
(SPEC 14.4.2, since 2.1.287), so both ship inline in every request:
`/context` then reads "MCP tools · 1.1k tokens" where it read "0 tokens",
the two definitions together (`compact`'s is about 2.1k characters), in the
prompt-cache prefix. Each answer is a line.

Known limits: the threshold is read once, at session start, so a window
changed by `/autocompact` mid-session is not followed; a model that keeps
working after the tool answered is compacted at whatever answered turn end
comes; the `resume` prompt enters under the plugin's name, as any
plugin-submitted prompt does.

## ask (`ask.tsx`)

The model asks the human through one tool, `mcp__doperpowers__AskUserQuestion`:
the built-in AskUserQuestion's input plus `async`. A blocking ask (`async`
false or absent) is AskUserQuestion: Claude Code's own dialog opens at once,
with the tab bar across the questions, previews, notes with `n`, "Type
something", "Chat about this" and the review page, and the call returns the
engine's own answer text, byte for byte what the built-in returns for the same
answers. The built-in is withdrawn while the tool exists: it waits behind tool
search, its name alone in the model's view, and a call of it is refused with a
sentence naming the new tool. An async ask (`async` true) returns at once and
the model works on; the questions wait in the transcript behind an `[ answer ]`
button, and pressing it opens the same dialog.

A plugin cannot call AskUserQuestion; it reaches the dialog through
`$.ui.ask`, which takes one question and raises an AskUserQuestion call that
every hook of the plugin but the calling one sees. The tool's hook raises it
with the first question and a token unique in the session as the header; the
mod's own `tool.call` hook on AskUserQuestion claims the call whose one header
is a pending token, only when the dispatch's origin is this plugin (an origin
the host sets and no plugin can write), and widens it to the whole question
set before the engine draws it. What that call's `next` resolves (the answer
text, or the refusal) is the tool's outcome. Every other AskUserQuestion call
from the model, or a stray one from this plugin, is refused; another plugin's
own `$.ui.ask` passes.

The tool's description is the built-in's own, as the engine computes it for
its `tool.describe` while the session starts, followed by one paragraph on
`async`; `$.tool.list()` gives only a tool's first 300 characters, which
stand in should the built-in not have been described yet. The tool is
registered at `session.start` of an interactive session and kept inline with a
`tool.describe` answer of `isDeferred: false`; the built-in's `tool.describe`
answers `isDeferred: true` with the withdrawal sentence, from the moment such
a session starts (the engine describes the built-in then, and caches the
answer for the session), and the built-in is put back should the tool fail to
register. A headless session gets neither, and neither does a MAWS launch
(`MAWS_NATIVE_TO_HUMAN` set), whatever its kind: MAWS offers its own ask tool,
`mcp__maws__ask`, and withholds the built-in on its launch line.

Every ask is validated before any dialog against the built-in's rules (1–4
questions, 2–4 options, the required strings, unique question texts and option
labels; never the header length, which the built-in does not check), and a
broken one gets the error the built-in's own validation would print, steer
for a lone option included; the engine does not check a plugin tool's input
against its schema, so this is the error the model reads. A subagent's call is
refused (subagents never have the built-in), and the agent definitions under
`agents/` withhold the tool.

Declining a blocking ask ends the model's turn, as declining the built-in's
does. Esc, Cancel on the review page, or Enter on an empty "Type something"
returns the engine's refusal as the call's error result; the rest of the turn's
model calls (one queued behind the ask in its batch, a second ask) are refused
before they run with `Not run: the human declined the question asked in this
turn.`, and the turn's next model request is not sent: a `turn.step` hook
aborts the turn there (`$.turn.abort`), which records nothing and draws
nothing beyond the call's row. "Chat about this" returns its refusal, with
what the human answered so far, and the turn goes on. The next turn starts
clear.

Pictures pasted into "Type something" reach the model as images. The engine
writes each paste into the session's pasted-image store
(`<temp root>/<project slug>/<session id>/images/<n>.png`, the folder prompt
pastes use) and marks the answer `(Image attached)`; the mod lists that
folder before and after the dialog. The store keeps a paste the human then
removed in the dialog, so the files alone do not say what was kept: the
engine's marks do, at least one picture per marked answer. When the marked
answers account for every new file, all were kept, and the tool returns the
engine's text block followed by one base64 image block per file, in number
order; when they do not (a picture removed, or two kept in one answer), which
were kept is unknown and none is sent, with a debug-log line. "Chat about
this" keeps its refusal, which is text, and appends one `[Image source:
<path>]` line per kept picture (the file's real path) for the model to Read.
The temp root is `claude-<uid>` under `CLAUDE_CODE_TMPDIR` or `/tmp`, found
as the one such folder this process can read; the slug and session id come
from the classic `SessionStart` payload.

Every call of the tool draws in the transcript as the engine draws the
built-in's: nothing while a blocking dialog is up, `⏺ User answered Claude's
questions:` with one `· <question> → <answer>` row per answer once answered,
`⏺ User declined to answer questions` with each question and its options once
refused. (The engine's own row is out of reach: a `ToolUse` rewrite to the
built-in's name draws a generic `AskUserQuestion(…)` line, and a `ToolResult`
rewrite of the tool draws nothing; so the mod draws the same lines itself,
reading the answers back from the engine's result text.) An open async ask,
which the built-in never has, draws `⏺ Claude asked (answer when ready):`, one
`· <header> — <question>` row per question and `[ answer ]`; once answered it
draws the answers, with `not delivered yet` under them until the answer has
reached the model. Above the prompt, while any ask is open, `2 open questions ·
[ answer ]` opens the oldest, since the ask's own row scrolls away while the
model works. That line is registered before the to-human view, whose band
draws without passing on, so it draws above it; the rows are registered after
the view, which keeps a question in the report.

Answering an async ask runs the blocking path from the press: the dialog is
raised inside the `ui.press` dispatch, as `$.ui.ask` requires, and queues
behind any dialog already up. Esc there means "not now": nothing is delivered
and the ask stays open. An answer, or "Chat about this" (its refusal text, the
human asking to talk the questions over), closes the ask and is delivered as
`The human responded to your async AskUserQuestion (call <id>): <the text the
blocking call would have returned>`, with one `[Image source: <path>]` line per
kept picture, since no route carries image bytes. While the session is idle it
goes as a prompt of the plugin's at once (`$.prompt.submit`), which the model
reads framed as the plugin's message. While a main-conversation turn runs it is
held, and every held answer goes out together, once, by the first of: the
result of the model's next call in the main loop (as `context`, which the model
reads right after the result; never a plugin's own call, whose context the
model never reads, nor a deny, nor a call the human's interrupt cut, whose
context the engine drops); the turn's end when the model answered (one prompt
carrying them all). A turn the human stopped (an interrupt, or a declined
blocking ask, which ends the turn with reason `aborted`) or that an error ended
keeps them: they ride with the human's next prompt as context, so a stop is not
undone by a prompt the mod submits. Each route takes the held answers in one
step; one that fails (a submission dropped or refused, the human's prompt
dropped beneath) puts them back ahead of any answered meanwhile, toasts why, and
leaves the next route to try.

A resumed session rebuilds its async asks from the transcript (the classic
`SessionStart` payload's path). Without a rewind every row of the file is
the conversation. Once the human rewound (the engine records it), only the
conversation the engine resumes counts, rebuilt as the engine rebuilds it:
back from its leaf parent by parent, across a compaction by the boundary's
logical parent, with the rows the engine restores beside that chain (the
results of a response's earlier calls, parented to their own call, and the
attachments under them); a branch the human rewound past, which stays in the
file, is left out. Every call of the tool with `async` true whose
result is the async one and whose input is valid is an ask; it reads answered
when a row the model read names its call in a delivery (a context attachment,
a prompt the plugin submitted, known by the engine's framing; never the
human's own prompt quoting one), else open. A transcript over the 4 MiB a
read takes is searched with `grep` for the stored forms resume reads; a search
that fails, or whose output is cut at the same 4 MiB, rebuilds nothing, with a
debug-log line. `/clear` forgets the asks; a compaction keeps them.

Known limits: a tool already running in parallel with the ask when the human
declines it finishes, where the built-in's abort would cut it; the refusal
reaches the model inside `<tool_use_error>`, the form every hook refusal takes,
where the built-in's is bare text; an image sits inside the tool result, where
the built-in puts it beside it, which reads the same to the model; a store that
cannot be placed leaves the answer text only, with a debug-log line; two
pictures kept in one answer, or a picture on a multi-select question (whose
answer the engine does not mark), are not sent; after a hot reload of the
plugin the store is not known until the next session start, and pictures go
as text only, and the async asks are forgotten (a resume reads them back); an
answer held when the session ends is lost with the process, and its ask reads
open on resume; an async picture reaches the model as a path it has to Read,
and the store is the engine's temp directory, cleaned with old sessions, so a
path delivered long after can be gone; the row reads its answers back from the
engine's text, so a question text that also appears inside an earlier answer
can misplace a row; the lines a search of a transcript over 4 MiB finds carry
no ancestry, so there a branch the human rewound past counts as the
conversation (its asks come back, its deliveries close theirs); and a rewind
inside a running session raises no event a hook sees, so the asks of the
branch it left stay in the row's and the band's view until the session is
resumed.

## secrets

`/secret KEY` moved to the `cua` plugin (SSFSKIM/cua, `hooks/mods/`) on
2026-10-07, so it is registered once, by the plugin that owns its store,
`~/.config/claude-secrets/KEY` (unchanged).

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
