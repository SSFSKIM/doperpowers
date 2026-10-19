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
  `message` label in Claude's orange. A span's body is the surface's own
  `Markdown` element, which draws as a reply's text does, so a table, a list
  or a code fence inside a mark draws as it would unmarked. The engine's own
  block is not handed back for it: on a remote surface (the desktop app,
  VS Code, mobile) a render answer carries one props, so of several blocks
  handed back only the first draws — Claude Desktop portals its native row
  into the first engine node and draws nothing at the rest, which left every
  span after the first label-only (2026-10-03) — and on the terminal the
  block carries the engine's row margin, a blank line between the label and
  the body (2026-10-14). The rows the view draws (a marked message, a
  `[ working record ]` button, the band above the prompt) stand one line
  below the row above, as the engine's own rows do. A
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
  can reach, and still draw. Re-checked on 2.1.300 (2026-10-15): the
  engine's attachment renderer raises no `ui.render`, `session.append` can
  rewrite an engine row's text but not drop it, and `prompt.attachment`
  changes only what the model reads.
- A question asked through `AskUserQuestion`, or through the ask mod's
  `mcp__doperpowers__AskUserQuestion` (an open async ask with its
  `[ answer ]` included), draws as it would unfolded (the question and the
  answer given) in the report itself: the answer is the human's own words,
  and they read it as they read a mark.
- Agent spawns stay in the report as the engine draws them: an `Agent`
  call and a `Workflow` of agents, and the notification that one of them
  failed (`Agent "…" failed: …`). `SendMessage` calls, received messages
  from agents, teammates or other sessions, and the other agent-finish
  notifications are working record. Unfolding the run or the full
  transcript reveals them.
- An API error that ends the main turn (retries spent, the context limit,
  a usage limit) stays in the report as the engine draws it: the model does
  not answer after it, so no message of its own could tell the human. The
  row's props do not mark it an error; the mod learns its text from
  `turn.complete` (`reason: "error"`) and the transcript's last assistant
  message, and redraws.
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

One tool the model can call, registered at `session.start` under the
plugin's name, `mcp__doperpowers__compact`: the model compacting its own
context at a checkpoint of its choosing. And its offer: at the end of each
main-conversation turn from 220k tokens on, once the context has grown 75k
since the last offer, the model is told its size and offered the
compaction, through the Stop hook. Below 300k the offer adds that
compacting is not necessarily recommended unless this is a clean
checkpoint, with no execution, decision or design pending that needs the
prior context whole.

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
do, why a checkpoint is worth compacting at, the token bands, when the
size is told, call it last and alone, end the turn).

The offer is a `classic.Stop` hook (matched on `hook_event_name: "Stop"`;
the settings hooks beneath, `smns-record.sh`, run first and their answer
stands beside it). It reads the figures — `$.session.usage` with the
`summary` breakdown: the last response's input tokens over the window the
engine compacts against (the compaction window where client data, a
setting or an experiment set one, as `/context` shows it under
"Auto-compact window", else the model's; estimated locally, no request
sent), and where the engine compacts on its own (that window less the 20k
output reserve and 13k headroom: 867k on the 900k window a 1M model gets
here, 167k on a 200k one) — and, where an offer is due, answers them and
the offer as the Stop's `additionalContext`. The engine's Stop runner
folds every output into a continuation (a block's reason, and an
additional context too, so nothing a Stop hook tells the model is free):
the offer reaches the model as a `<system-reminder>` opening `Stop hook
additional context:` (an attachment row in the transcript,
`hook_additional_context` on `Stop`), and one more step of the same turn
runs. A context rather than a block because of what the person sees under
"Ran 1 stop hook": a context draws as `Stop hook feedback: …` in gold, a
block as `Stop hook error: …` in red (live, 2.1.302; both reach the model
and continue alike). The model calls `compact` (the request pends, and the
turn's end compacts as above) or replies "Not compacting." (a line, asked
for because an answer with no text costs the engine's "no visible output"
nudge, a step more); the Stop after that step carries `stop_hook_active`
and passes, so an offer is one step and no loop (the engine caps
consecutive continuations at 8 regardless). The gate is `OFFER_GATE`: floor 220k, below the 300k
where the tool's guidance turns to "any reasonable checkpoint"
(`EARLY_BELOW`, under which the offer carries that caveat), so a clean
checkpoint before it is not missed, and step 75k, so a
conversation adding a few k a turn is not asked every turn while a working
turn, tens of k, is asked each time. The offer's baseline resets when a
main-conversation `session.compact` stands (not a skip or a `precompute`,
which replaces no conversation), and when this mod's own compaction stands.
As a backstop for an engine path that compacts without the event, a figure
below the last offer's at any Stop resets it too, even below the floor.
`DOPERPOWERS_COMPACT_OFFER_FLOOR` and `_STEP` (whole tokens) override a
launch's; 0 and 0 is an offer at every turn's end. No
offer when a hook beneath sets `preventContinuation` (its answer passes
through unchanged, without spending an offer), while a request pends, on a
subagent's Stop (`SubagentStop` is another event, and a subagent cannot
compact), in a session without the
tool (headless), or when the figures cannot be read (logged). The free
`context_usage` tool the model used to ask the figures with was retired
with the offer (7.184.0): the offer carries them, and the tool's
description says when they come — until the first offer the model is under
the floor, and it may compact unasked at any checkpoint.

A subagent's call to `compact` is refused (its turn ends are not the main
conversation's). A headless (`-p` / SDK) session gets no tool: the engine
has no compactor a plugin can call there yet. The shared session and turn
events are taken with matchers (`isInteractive: true`, `trigger: /^/`,
`reason: "answer"`) because kairos, agents and bridge register them too,
and the engine admits one
unmatched registration of an event per module.

The tool is an MCP tool to the engine, which tool search defers (the model
sees the name alone until it loads the tool with `ToolSearch`), so the
guidance in its description would reach the model only once it had already
thought of compacting. A `tool.describe` hook answers `isDeferred: false`,
which the engine takes over its own placement (SPEC 14.4.2, since 2.1.287),
so it ships inline in every request: the definition (about 2.1k
characters) in the prompt-cache prefix, where `/context` counts it under
"MCP tools". Its answer is a line.

Known limits: the threshold is read once, at session start, so a window
changed by `/autocompact` mid-session is not followed; a model that keeps
working after the tool answered is compacted at whatever answered turn end
comes; the `resume` prompt enters under the plugin's name, as any
plugin-submitted prompt does; an offer's step is a model call over the
whole context (a prompt-cache read, mostly), the price of a decision at the
turn's end, and in a session the person watches the decline line shows
under the answer. Live check: `tests/mods/live-compact-offer-check.py`
(spends model calls; run by hand).

## appeal (`appeal.tsx`, `appeal-judge.tsx`)

In auto mode the classifier blocks calls, some wrongly — a scratch file
under `/tmp` read as a shared resource, a subagent's force-push the human
asked for in the main conversation, which a subagent's classifier never
sees. This mod lets the agent contest one block to an independent judge.
Design and the engine facts it stands on:
`docs/doperpowers/specs/2026-10-17-auto-mode-appeal-design.md`.

A `tool.call` hook on every tool reads the classifier's denial out of an
error result (`Permission for this action was denied by the Claude Code
auto mode classifier. Reason: …`), gives the block an id (`b1`, `b2`, …)
and adds one `context` line telling the model it may appeal once. A block
naming `[Data Exfiltration]` (the classifier's hard block) or `[User Deny
Rules]` (a `permissions.deny` rule reached by another route) gets neither.
`mcp__doperpowers__appeal` (`block`, `argument`), registered in every loop,
subagents included, puts the appeal to the judge: one `$.model.complete`
call, `opus` at high effort (`DOPERPOWERS_APPEAL_MODEL` overrides), whose
system prompt is the judge's whole behavior (`JUDGE_SYSTEM` in
`appeal-judge.tsx`). It reads the blocked call whole (an input over 100,000
characters is refused before the judge), the argument named as the agent's
claim, the instruction files (`~/.claude/CLAUDE.md` as the user's own, the
project's as in the repository), the `autoMode` and `permissions.deny` of
the settings sources the classifier itself trusts — `user`, `policy`,
`flag`, read one at a time, never the merged ones a repository's
`.claude/settings.json` feeds — the answered async asks (the ask mod's
`asyncAsks()`: an answer delivered as a tool result's context is not the
user's words to the classifier, which is how this very feature's spec was
blocked as `[Auto-Mode Bypass]` after the human chose it in one), and the
main conversation as lines — `[user]` rows with `<system-reminder>` spans
cut, the agent's last text before each as the proposal the user may have
affirmed, each call and its result — with a subagent's conversation after
it for a block made there. A compaction summary and a plugin-submitted
prompt, which `$.session.messages()` hands over as user rows, are named as
not the user's. The judge grants only when the block misread facts the
evidence shows, or the user's own words authorize the exact action; two
bars no authorization clears (sending sensitive material out, reaching a
deny rule's effect); when in doubt it upholds and says what the user would
need to say. A main-loop grant is run by the appeal itself through
`$.tool.call` — the plugin's own call, which the engine runs in the
session's loop and, in auto mode, past the classifier by its plugin-origin
fast path, the deny and ask rules still applying — and the result is the
appeal's; the model does not re-run it. A subagent's grant leaves a pass
instead, since a plugin's call would run in the main loop's shell and
directory, not the subagent's: the identical call (for Bash, its
`description` aside) in the same loop and directory, within 10 minutes,
once, and for Bash before any other Bash call in that loop. The
`tool.check` hook applies it only over core's plain `ask` — no `rule`,
`hook`, `setting`, `decider`, no organization `ceiling` — so a pass never
overrides a deny rule, a settings ask rule, a classic hook, or a host. Any
`prompt.submit`, and any answer to a question, ends every pass and makes a
judge call in flight no ruling: the ruling was on the conversation as it
was. One appeal per block; a judge call that fails leaves the appeal open
once more. Every event is logged to
`~/.claude/appeals/<session-id>.jsonl` (seeded from the file at start, the
writes chained), and `/appeals` prints the last 30 days — counts, the grants,
and the `autoMode` entries one more model call suggests from them, for the
person to apply by hand; nothing here writes settings.

Tests: `tests/mods/appeal.test.ts`; the live check
`tests/mods/live-appeal-check.py` drives a headless auto-mode session
through a real block, ruling and pass (it spends model calls; run by hand).

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

An async ask can also be answered from outside the terminal (`sminos answer`,
later the web): the bridge hands the answers to `answerAsync`, which refuses
one already answered or whose dialog is up, and otherwise delivers them by the
same routes as a press's.

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
read takes is searched for the stored forms resume reads, by one `perl` pass
(macOS's `grep` slows with each pattern: 7 s against 0.3 s on a transcript of
144 MiB), or by `grep` where perl does not start; a search that fails, or
whose output is cut at the same 4 MiB, rebuilds nothing, with a debug-log
line. `/clear` forgets the asks; a compaction keeps them.

A copy of a session (`--fork-session`, a `--bg --resume` while another
process holds the session, `/branch`; the payload's source `fork`) starts
under an id of its own, its transcript unwritten until its first row, and
nothing a module reaches names the session it copied. Its asks are rebuilt
from the conversation the engine holds: the calls and their results from
`$.session.messages()`, and an answer given as a tool result's context, which
is no row there, from the model's form (`{ as: "api" }`), inside that result.
That conversation starts at the last compaction, so an ask from before it is
not rebuilt in the copy; the original keeps it.

Known limits: a tool already running in parallel with the ask when the human
declines it finishes, where the built-in's abort would cut it; the refusal
reaches the model inside `<tool_use_error>`, the form every hook refusal takes,
where the built-in's is bare text; an image sits inside the tool result, where
the built-in puts it beside it, which reads the same to the model; a store that
cannot be placed leaves the answer text only, with a debug-log line; two
pictures kept in one answer, or a picture on a multi-select question (whose
answer the engine does not mark), are not sent; a reload of the plugin
takes up the asks, the undelivered answers and the store from `$.state`, and
an answer on its way to the model at the reload is held again, so it may
reach the model twice but is never lost; an answer held when the session
ends is lost with the process, and its ask reads open on resume; an async picture reaches the model as a path it has to Read,
and the store is the engine's temp directory, cleaned with old sessions, so a
path delivered long after can be gone; the row reads its answers back from the
engine's text, so a question text that also appears inside an earlier answer
can misplace a row; the lines a search of a transcript over 4 MiB finds carry
no ancestry, so there a branch the human rewound past counts as the
conversation (its asks come back, its deliveries close theirs); and a rewind
inside a running session raises no event a hook sees, so the asks of the
branch it left stay in the row's and the band's view until the session is
resumed.

## bridge (`bridge.tsx`)

The session, reachable from outside it on this machine: its live stream for
a reader, and its control for a client, through an endpoint of its own. At
`session.start` the mod spawns a child for the session's life, `sminos
bridge --session <id>` (`skills/sminos/scripts/sminos_bridge.py`), which
serves HTTP on `$SMINOS_HOME/bridge/<id>.sock`; the socket answering is the
session's bridge presence. The mod posts the session's events to it and
reads commands from the child's stdout, one JSON line each. The protocol,
routes, events and their fields are DX5, in
`docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`. It registers
first in `register.tsx`, so its hooks are the outermost: what it reports is
what the session showed and kept, after every other mod. Never in a session
with `SMNS_INTERNAL` set (derive's headless fork).

`bridge.tsx` holds the hooks and the code that takes `$`: the session start,
the child and the session it serves, control, and the wait for a decision.
The rest sits beside it in modules that take no `$`, each importing only the
ones listed before it: `bridge-state.tsx` (the one state object, its types,
and `resetBridge`), `bridge-stream.tsx` (the mod's copy of the live state and
the poster), `bridge-requests.tsx` (requests from outside and their
settlement), and `bridge-rows.tsx` (each kept row's notice, a compaction's
rows read from the transcript, and the export to the host).

- **The stream.** Each chunk of every model request, the main loop's and
  every subagent's (tagged with its turn, loop and index), tool calls and
  results, turns, subagents, usage, a heartbeat, and the requests below.
  Every row the session keeps is named once, as it is written (so in write
  order): a response row by its `block-row` (which settles its block), any
  other by `row-seen`, and a step's end follows every `block-row` of its step
  (held, a second at most, for a row the engine appends after the request's
  result); each loop's last notice is the snapshot's `cut`, so a reader
  joining the transcript on disk with the stream knows which rows are
  accounted for. A manual compaction's rows (the person's `/compact`, the
  bridge's `compact`, the compact tool's) pass no `session.append`: once the
  compaction stands, a hold in the post queue keeps everything later back
  while the child reads them from the transcript (`GET /rows`, past the
  loop's cut, until the summary row the compaction's result names is on
  disk), and their `row-seen`s take its place. A loop older than the module (a reload, a resume, a
  subagent running at load) is cut first at its transcript's tail, which the
  module's first child reads (its hello's `seed`), and a model request of it
  begun before that hello streams to nobody: its rows reach a reader through
  the transcript. A loop the module saw from its first row is cut by its
  notices alone. The mod keeps its own copy of the live state and opens
  every new child, and every post after a lost one, with a `resync`; the
  child ends every subscription when a later one comes, and a subscriber
  starts over from a fresh snapshot. Posts run from one loop started at
  `session.start`: a fetch begun inside a hook dies with that hook's
  dispatch (an Esc, an interrupt). Each carries the nonce the child's hello
  named: a reload's old module, still posting to the session's path, is
  turned away (409) and stops.
- **Control.** `steer` appends a user row the loop reads at its next request,
  the owner's words under the line `[sminos steer from human]`, by which a
  reader of the transcript tells it from the bridge's other rows (the running
  tool goes on; a turn that answers before reading it is woken once);
  `interrupt` aborts the turn and stops each Bash call the abort moved
  to the background, then appends a user row telling the model so (a
  plugin's abort leaves no marker of its own, and the moved call's result
  says it runs on), holding the turn's Bash calls until the row is in, since
  a queued next turn takes its messages before it waits for any hook;
  `model` rewrites the main loop's requests (never
  `$.config.set`, which is the user's default); `compact` runs at once, or at
  the end of a running turn; `deliver` submits a log event as the human's
  words, once per `(writer, seq)`.
- **Requests from outside.** A permission prompt or a question the engine
  puts to its dialog is raised, and its `PermissionRequest` hook long-polls
  the child for a decision while the terminal's dialog stays up; an async
  question of the ask mod is raised as it opens, or as the bridge starts when
  it was open before (a resumed session's, which the ask mod reads back while
  the session is still starting; a reloaded module's), and answered through
  the ask mod's external path (`answerAsync`). Each ends with one `settled` naming
  the side whose answer the engine used, read from the engine's
  `tool_decision` record of the call (raised to the mod through
  `telemetry.log`), else the transcript's mark of a hook's decision.
- **Messages to the host.** The main loop's rows that may carry one — a text
  row with a mark, an async ask with its result, a row that may answer one
  (the ask mod's delivery, as its prompt row or a context attachment; a MAWS
  steer, as the human's prompt or taken into a running turn) — go to the
  child in the shape the transcript keeps them (an attachment's payload read
  back from its rendering, all the hook is handed of it, by stripping the
  engine's exact framing; one not so framed, or holding the engine's `&lt;`
  escape, is left to the Stop hook), and the child appends their
  `message`, `question` and `answered` events to the project's log through
  `sminos record`'s own writer and `(kind, src)` keys, so they reach the log
  as they are written and the Stop hook's export finds them there.

From another terminal: `sminos watch|steer|interrupt|model|compact|decide|answer
<member>`. Live checks under `tests/mods/live-*-check.py` run real sessions
(they spend model calls; run by hand).

Known limits: a module reload kills the child and starts the module's state
empty, so no response streaming at that moment, nor one begun before the new
child's hello, is streamed (its rows are named as they are written, and a
reader takes them from the transcript); a turn running across a reload is
taken back at its next model request (interrupt, steer and compact act on it
from there, and the stream gets its start marked `recovered`); until then, or
until the turn completes or the session's engine record says idle, the module
does not know whether a turn runs, and those three verbs are refused with
"turn state unknown since the bridge reloaded; retry after the next model
request" (exit 1), never answered as idle; calls begun before the reload are
not the new module's (an interrupt's abort stops them, but none the abort
moved to the background is stopped after it); a text row or an answer past 65,536 characters is left to the Stop hook's export;
a `--bg` job starts in permission mode `auto`, where most calls raise no
request; the plugin's own append passes no hook of the plugin's, so the
steer's row is named from the append's answer, after it is written; a
compaction's rows whose summary row is not on disk within 1.5 seconds are
named by none, and a reader emits them unnamed, on the next notice of their
loop or after 2 seconds; a hook's success with nothing to say is raised to
the hook but never written, so it is named by none.

## interim (`interim.ts`)

A subagent that ends its turn while its own background shell, monitor or
workflow still runs makes the engine send its parent a completion
notification anyway, and again each time that work wakes it and it stops to
wait once more. Each one is a parent turn spent on "still running, nothing to
do": in two sessions read on 2026-10-17 they were 597 of the turns, about
190M tokens of cached context re-read, from subagents parked on test suites, CI
gates and wait scripts. By 2.1.300 the engine's summary says `is waiting on
its own background work` rather than `finished`; the wake is the same. The
engine marks them, writing "This agent stopped with background work of its
own still running" into the notification's `<note>` (the final one carries
the other note), and a `prompt.submit` hook matched on `origin.kind:
'task-notification'` drops one before it enters the session only when all
three of these hold.

- The text is the engine's envelope alone, status `completed`, that note,
  and a `<result>` that is wholly the waiting placeholder ("This agent has not
  reported yet: ... through SubagentHandback when that finishes."). The
  pointer placeholder ("This agent's report was delivered to you as a
  message ...") passes: when the agent the report went to has ended, the
  engine moves the notification to the main session but not the report, so
  the pointer can name a message the session never got, and a pointer routed
  to the main session the engine already queues without waking it.
- The placeholder is the engine's. The engine writes it only for a run under
  the hand-back contract; outside it (a fork, a run not in auto mode) the
  agent's own words stand, and they could be that very sentence. So the
  agent's transcript is read as the engine reads it at each run's start: the
  latest meta user record that opens with the hand-back reminder or with its
  countermand must be the reminder. A compaction after both ends the reading
  unanswered, since the engine's own view of the run starts there. The
  transcript is where the notification's `<output-file>` link lands (a
  subagent's `.output` is a symlink to it), which must be
  `agent-<task-id>.jsonl`; `grep` searches it, as it runs far past the 4 MiB
  `$.fs.read` takes. All 725 waiting notifications in the two sessions below
  carried the line, each linking to its agent's transcript; the engine
  leaves it out for an unreadable output or saved web-fetch files, and then
  the notification passes.
- It tells the session nothing its conversation does not hold. The session
  knows the agent when its own loop spawned it (`$.agent.list()` gives no
  `parentId`). An orphan's notification, fallen back to the main session
  when the agent that spawned it ended, is the session's first sign of it,
  so one drops only once the conversation holds an earlier notification of
  that task; and one carrying a `<worktree>` drops only once the
  conversation holds an earlier notification carrying the same worktree,
  since the launch never says where an isolated agent's work lives. The
  conversation is read as it stands, `$.session.messages({ as: "api" })`:
  the engine's live messages from the last compaction on, a rewind applied,
  the newest 4096 messages. A notification that started a turn is a user
  message's text there. One that came in while a tool call ran (the rows
  form leaves those out) the engine folds into that call's result, in a
  `<system-reminder>` of its own under its system-notification frame
  ("[SYSTEM NOTIFICATION - NOT USER INPUT]" and the four lines after it, the
  same text from 2.1.283 to 2.1.302), opening the result or after a blank
  line. In a tool result a notification counts only so, directly under the
  frame and alone in its reminder, so a tool's output that quotes one (a
  file read, a grep of a transcript) does not. So a notification rewound or
  summarized away, refused or answered by a hook beneath before it reached
  the session, or rewritten there without its worktree, is not held, and
  the next one passes; so is one folded under a frame a later engine
  rewrites, until the match learns the new text.

Every check fails open: a lookup that errs or cannot tell (no
`<output-file>`, a link that is dangling or lands anywhere but the agent's
transcript, an agent the list does not name, a conversation that cannot be
read, `grep` missing, failing, past 10 s or cut at 4 MiB, a line that does
not parse) lets the notification through, and so does a hook that throws.
The hook keeps no state, so a reload into a running session (a plugin update
and `/reload-plugins`) filters from its first notification. Replayed over
those sessions, each main transcript read in order (engine 2.1.283 to
2.1.301; the agent list taken from each agent's meta file, the `.output`
links still on disk, the conversation rebuilt from the notifications the
hook let in and emptied at each of the 65 compactions, rewinds and the
4096-message window not modeled), the filter drops 551 of 749 interim
notifications, where the text alone dropped 745: 20 pointers pass, 133 whose
worktree the conversation did not hold yet, 41 orphans' with no earlier
notification there, and 4 carrying the safety classifier's warning. Every
parked agent's transcript held the reminder, so telling the engine's
placeholder from an agent's cost no drops. That replay put a notification
that came in mid-turn into user text, which the filter first read only in
7.171.1, when it learned the fold: replayed over a later session with the
filter live (MAWS `37052769`, engine 2.1.302, 50 interim notifications),
each mid-turn one folded into the running call's result as the engine folds
it, the earlier filter reproduces every live decision (44 drops), and the
fold adds 4 drops, each a worktree repeat whose path an earlier
notification of that task, folded mid-turn, had already given, each agent's
report reaching the session later. Across this machine's transcripts no
stored tool result reads as a fold, though 496 in the 2,612 files that carry
the frame quote a notification, 3 of them with the frame itself.

What it gives up: the parent no longer sees that the agent parked again. An
agent killed while parked gets no notification either way, since the engine
counts the interim one as its notice when it queues it, before any hook
runs, so the parent hears of the kill only if it did the killing or looks.
The transcript read can misjudge whose sentence the placeholder is in two
cases: a fork, whose own contract is off while its transcript inherits its
parent's reminder, and a notification still queued from an earlier run after
a permission-mode change let a later run write the reminder. In either, what
the filter drops is an agent's whole answer that is, byte for byte, the
engine's waiting sentence; no report is in it. Reading a notification folded
into a tool result trusts the engine's frame: a tool's output that ends, after
a blank line, with that exact frame and a notification carrying a live
agent's task id and worktree, alone in a reminder of its own, counts as the
engine's, and that agent's first notification of the worktree (or an
orphan's first) drops. What is lost is a placeholder, never a report; the
worktree and the orphan come again with its report and final notification.
Each drop still leaves a line
in the transcript, "Prompt dropped by a hook: interim agent notification:
its work is still running": the engine writes a `system` notice at level
`warning` for every `prompt.submit` that ends without entering (a hook's
answer without `next` reads "Prompt not submitted"), and draws it through a
component no render hook reaches, so neither the engine's view nor the
to-human view can fold it. `session.append` can rewrite a stored row's text
but refuses only a plugin's own append, and `session.receive`, which can
take a delivery without a trace, sees deliveries from outside the process,
never an agent's notification.

## address (`address.tsx`)

Every commit and pull request a session writes carries its sminos address, so
whoever reads the artifact later — the owner, another session — reaches the
session that made it in one step: `sminos who <commit|PR>` reads the line back
and says who that session is now and how to reach or resume it. The engine
composes the attribution text the model is told to end a commit message and a
PR body with (the settings' `attribution`, and its own `Claude-Session:`
trailer for a remote or bridged session) and passes each through
`attribution.text`; the mod adds `Sminos-Session: <alias>#<short> (<project>
on <machine>)` — to a commit as a git trailer (in the trailer block when the
text ends in one, a paragraph of its own otherwise), to a PR body as its last
line. With the settings' attribution empty the line stands alone, and the
engine still tells the model to write it: the reminder is built whenever the
composed text is non-empty (checked live on 2.1.303, in an interactive
session, a `--bg` job and `claude -p`, the main loop and a subagent alike).

The line is the CLI's, `sminos who --session <id>`, which composes it where
the identity lives (the alias the session's own `say` signs with, its project,
the machine's enrolled name; the short alone, `Sminos-Session: <short>
(<project> on <machine>)`, for a session with no name fit for a line, such
as a `claude --bg "<prompt>"` job that joined under its prompt) and prints
nothing for a session in no project,
an internal fork (`SMNS_INTERNAL`), or one that is no member (a headless run
its host did not mark). The engine asks before every model request of every
loop, twice (commit, then pr): the mod keeps the line and asks the CLI again
only for a new session id (a session sent to the background goes on as a new
one) or once the kept line is a minute old (an alias renamed mid-session); a
CLI that cannot run keeps the line it had. A subagent's request reads the
parent's session id, so a subagent's commits carry the session someone can
reach. The engine re-sends its reminder only when the text changes.

## reload (`reload.tsx`)

A plugin update reaches a running session without the person typing
`/reload-plugins` in it. The engine (2.1.302) parses
`installed_plugins.json` once per process, and nothing tells session B that
session A installed a new version: `claude plugin update`, a merging
session's roll, or a new session's marketplace auto-update (once per
process, 0–10 minutes after its first prompt) all leave every other session
on the version it loaded. `/reload-plugins` loads the plugins again, so it is
the one step missing. It does not load them from their records: a plugin its
marketplace carries by path (doperpowers' `./`, eli5's `./eli5`) loads at the
version its manifest in the marketplace clone names, from that version's
cache directory, made from the clone where it is missing (2.1.302:
`NMe({ cacheOnly: false })` → `Yzn`; a record's install path is read only by
the cache-only load at startup), and a record pointed at a copied directory
still loaded `…/eli5/1.0.0`. The record is the signal that a new version
landed: `claude plugin update` and the auto-update both write it, and in the
normal flow it names the version the clone carries. A reload moves every
path-sourced plugin to its clone's version, including one whose record
nobody updated.

In an interactive session the module reads, at start, what the session runs
of each installed plugin the settings enable: the record the engine loads
it from (the first that applies whose directory exists; a user or managed
record applies everywhere, a project or local one at its path or under its
git root), and for doperpowers itself the directory it runs from, which is
exact where the file has moved on. Every 15 s it stats the file; once the
file has been quiet one period after a change (a roll of several plugins
reloads once), it reads it again, and when a plugin the session runs has
another install path there it toasts what changed (`doperpowers 7.186.0 →
7.187.0: reloading plugins once the session is idle`) and calls
`$.command.run({ command: 'reload-plugins' })`, which the engine queues
until the session is idle and runs as a typed command: the person and the
model read its output row (`Reloaded: N plugins · …`), and no model turn
runs. A reload stops no running work: subagents, background shells,
Monitors and the MCP servers of unchanged plugins carry on, and the old
version's cache directory stays marked in use until the process exits. It
does cost the bridge a restart: a reload into a new doperpowers starts its
modules again, which kills the bridge's child and spawns the next, ending
every subscription to the session with `discontinuity`, and the plane's
subscriber subscribes again. Every idle session on the machine reloads
within half a minute of one install, so each `sminos watch` and desk view of
them resubscribes once, briefly.

One reload per state of the file: a plugin whose new version does not load
is not reloaded again until the file changes. Only a change after the
module loaded is acted on, so the module a reload starts never reloads on
its own. A reload the engine refuses (after an Esc, with no input since; a
stop that dropped it) is tried again a minute later; the toast comes once
per state of the file, so a person reading after an Esc sees it once, and
each retry goes to the debug log. A reload that would add or remove a
plugin MCP or LSP server is aborted by the engine, since the next message
would re-read the whole conversation; the module never passes
`--force`, and says so in the transcript instead. The reload waits while an
ask's dialog is up: the module that raised the dialog takes its answer, and a
module the reload started meanwhile would show the ask open still. Open
async questions and undelivered answers no longer hold it, since the ask mod
keeps them across the reload. An uninstall is not acted on, nor a newly
installed plugin; a copy run from outside the plugin cache (`--plugin-dir`)
is not watched, since the engine watches that folder itself.

The module also fetches what the engine fetches only at a session's start.
For each marketplace `known_marketplaces.json` marks `autoUpdate` (from
GitHub or a git URL; this machine's are doperpowers, cua, designer and
ptc-tool), one session per machine at a time, at most every 5 minutes,
reads the remote's head with `git ls-remote` (an entry whose URL or ref
begins with `-` is skipped) and compares it with the marketplace clone's.
Where it moved, it runs `claude plugin marketplace update <name>` and then
`claude plugin update <key> --scope user` for each enabled plugin installed
from it at user scope; the watch then reloads every session on the machine.
Each session looks once a minute whether the machine's fetch is due:
`~/.claude/autoreload/fetch.stamp` is older than 5 minutes, and the lock
directory beside it (`fetch.lock`, made with `mkdir`) is free. The lock
serializes this module's sessions only, and the engine takes none: it saves
`installed_plugins.json` and `known_marketplaces.json` by read-modify-write,
and refreshes a marketplace by cloning beside its clone and renaming the new
one in (2.1.283 on; earlier engines pulled into the clone). The fetch is due
exactly when the remote has just moved, which is when the person or the
merging session runs its own update, or a new session's auto-update runs.
So the session holding the lock first looks whether either file, a clone's
parent directory or its `.git/FETCH_HEAD` changed within the last minute; if
one did, another actor is rolling, and the round is skipped without a
stamp, for a later look to try again. That narrows the race without closing
it: an actor that starts after the look still runs beside the fetch. The
stamp is written before the fetch, so a fetch that fails waits out the
period rather than being retried by every session, and a lock left by a
session that died is cleared after 30 minutes. A machine with nothing
new costs one `ls-remote` per marketplace every 5 minutes, about half a
second each. It never passes `-y`, so a marketplace whose install command
changed waits for a person.

`DOPERPOWERS_AUTORELOAD=off` (or `0`, `false`) leaves a launch on the
versions it loaded and fetches nothing. Headless runs (`-p`, the SDK, MAWS)
are left out: the engine refuses a plugin's `/reload-plugins` there.

## secrets

`/secret KEY` moved to the `cua` plugin (SSFSKIM/cua, `hooks/mods/`) on
2026-10-07, so it is registered once, by the plugin that owns its store,
`~/.config/claude-secrets/KEY` (unchanged). The guard that keeps secrets out
of what the model reads and what the transcript keeps is the devcloud
plugin's (`devcloud/hooks/mods/secrets.tsx`, described in
`devcloud/README.md`), a separate plugin a person opts into.

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
