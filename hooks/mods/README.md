# mods

Function hooks of the doperpowers plugin: one module (`register.tsx`, named
by `hooks/hooks.json` under `modules`) that registers its mods —
kairos, compact, appeal, interim and reload, each described below. The
engine loads it only where `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set and
ignores it elsewhere; the shell hooks beside this folder run everywhere. The
ask tool, the bridge and the session's sminos address are the sminos
plugin's mods (`sminos/hooks/mods/README.md`); the to-human view, described
first here, is the to-human plugin's (`to-human/hooks/mods/to-human.tsx`).

## to-human (`to-human.tsx`)

The `to-human` output style (`output-styles/to-human.md`) assumes a human who
reads a report stream, not the transcript: the model sends them messages in
`<message>` at a turn's end and, before a tool call, through the to-human
plugin's message tool (`to-human/hooks/mods/message.tsx`,
`mcp__to-human__message`, which the view draws as a message where the call
sits), asks for what it needs from them through AskUserQuestion (the
ask mod's, `async` when it can work on while they decide), and leaves its
working record unwrapped. The old `<to-human>`, `<essential>`,
`<need-input>` and `<insight>` marks read as aliases of `<message>` (an old
question's `<choice>` lines stay in its text, with no buttons); tags in inline code or fenced blocks stay literal. This mod
makes the Claude Code terminal the consumer of those marks.

Under MAWS (`MAWS_NATIVE_TO_HUMAN` set) this view draws on MAWS's surfaces as on any other: MAWS shows the mods' report and draws no message cards of its own. The flag still keeps the message tool unregistered (MAWS registers `mcp__maws__message`), and the streaming hook draws nothing.

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
  `› working record` button, the band above the prompt) stand one line
  below the row above, as the engine's own rows do. A
  span still streaming shows `…` after its label. A message with an unmarked
  working record beside its spans gets a dim `› working record` button that
  unfolds the engine's drawing of the whole block, and the run of working
  record after that message opens and closes with it: the message is where
  the run starts, so two things the person reads have one button between
  them, never the message's and the run's stacked.
- Messages with no marks at all, tool calls with their results, and prompt
  rows that are deliveries of the model's own business rather than the
  person's words (a background command's or a monitor's notification, a
  schedule firing) are working record, and a run of it draws one
  `› working record` button rather than one button per row: the run breaks
  at the person's own prompt, at a message that carries marks (one with
  record beside its marks starts the run itself), and at every row of the
  next two bullets, so what stands between two things they read opens and
  closes as a unit. The button is drawn by the row the run starts at and the
  rest of the run draw nothing;
  unfolded, the run shows the engine's own rows as the transcript draws them
  (a group of reads keeps its count line: each call in its place would be
  the ctrl+o form, its whole output inline; where the engine expands the
  group itself, in the ctrl+o transcript and under `--verbose`, each call is
  a row of its own in the group's run), with `‹ fold to report` under the
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
- A question asked through `AskUserQuestion`, or through the sminos ask
  mod's `mcp__sminos__AskUserQuestion` (an open async ask with its
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
- Above the prompt, `to-human view · full transcript ›` switches the whole
  transcript to the engine's drawing; the same button then reads
  `report only ›`.

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
main-conversation turn from 300k tokens on, once the context has grown 70k
since the last offer, the model is told its size and offered the
compaction, in a prompt the plugin submits. Below 300k, which only a launch that
lowers the floor reaches, the offer adds that compacting is not
necessarily recommended unless this is a clean checkpoint, with no
execution, decision or design pending that needs the prior context whole.

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

The offer is a prompt the plugin submits (`$.prompt.submit`) at the
`turn.complete` of a main-conversation turn the model answered and asked no
compaction in. It reads the figures there — `$.session.usage` with the
`summary` breakdown: the last response's input tokens over the window the
engine compacts against (the compaction window where client data, a
setting or an experiment set one, as `/context` shows it under
"Auto-compact window", else the model's; estimated locally, no request
sent), and where the engine compacts on its own (that window less the 20k
output reserve and 13k headroom: 867k on the 900k window a 1M model gets
here, 167k on a 200k one) — and, where an offer is due, submits them and
the offer. The engine runs a plugin's prompt as a turn of its own once
the session is idle, behind any prompt the person queued (theirs is
`next` priority, a plugin's `later`), and the model reads it as "The
doperpowers plugin sent a message: …". It was the Stop hook's
`additionalContext` until 7.192.0, one more step of the same turn; the
engine draws that as a gold "Ran 1 stop hook ⎿ Stop hook feedback" row,
which no render hook reaches and the to-human report view cannot fold,
while the view folds a plugin's prompt, and the model's reply to it, into
the working record. The model calls `compact` (the request pends, and the
end of the offer's turn compacts as above) or replies "Not compacting." (a
line, asked for because an answer with no text costs the engine's "no
visible output" nudge, a step more).

The offer's own turn ends with no offer: the module's `prompt.submit` hook,
matched on the plugin's own origin, knows an offer by its text (it opens
on the figures and asks for the decline line, so a module reloaded while
its offer waits still knows it) and marks the turn it starts as the
offer's; the resume prompt passes it untouched. While an offer waits to
enter, no other turn end offers, so a prompt the person queued during the
turn runs first and ends with no second offer; the same hook then reads
the figures again and rewrites the offer's text, so it carries the context
as it stands when the model reads it, and that figure becomes the last
offer's. When a compaction stood between the offer's submission and its
entry (a `/compact` the person queued, the model compacting in a turn the
person queued ahead of it), or there is no figure to read (the engine has
none until the first response after a compaction), the offer enters
saying the context was compacted since and there is nothing to decide, and
the model replies "Not compacting.": it is not dropped, which would draw
the engine's "Prompt dropped by a hook" notice. An offer that never ran
because it never passed the hook (the engine removed it from the queue,
settling it as "removed from the queue before it ran", or a hook above
answered it) gives its step back: the baseline returns to what it was,
unless a compaction has started it over since. One a hook beneath refuses
(a hook's drop, a settings hook's block) stays spent, so a hook that
always refuses costs no submission every turn. Either way it stops
waiting, logged to the debug log. The `classic.Stop` hook
(matched on `hook_event_name: "Stop"`) only reads what the settings hooks
beneath answered (`smns-record.sh` keeps its say): one that set
`preventContinuation` withholds the offer at that turn's end without
spending it. A Stop answered with nothing added draws no row.

The gate is `OFFER_GATE`: floor 300k, where
the tool's guidance turns to "any reasonable checkpoint" (`EARLY_BELOW`,
under which an offer carries that caveat), so below it the model compacts
unasked once the work at hand is done and no turn is spent on an offer,
and step 70k, so a
conversation adding a few k a turn is not asked every turn while a working
turn, tens of k, is asked each time. The offer's baseline resets when a
main-conversation `session.compact` stands (not a skip or a `precompute`,
which replaces no conversation), and when this mod's own compaction stands.
As a backstop for an engine path that compacts without the event, a figure
below the last offer's at any turn's end resets it too, even below the floor.
`DOPERPOWERS_COMPACT_OFFER_FLOOR` and `_STEP` (whole tokens) override a
launch's; 0 and 0 is an offer at every turn's end but the offer's own. No
offer at a turn that ended interrupted or on an error (the matcher's
`reason: "answer"`), when a Stop hook beneath set `preventContinuation`,
while a request pends, at a subagent's turn end (`SubagentStop` is another
event, and a subagent cannot compact), in a session without the tool
(headless), or when the figures cannot be read (logged). The free
`context_usage` tool the model used to ask the figures with was retired
with the offer (7.184.0): the offer carries them, and the tool's
description says when they come — until the first offer the model is under
the floor, and it may compact unasked at any checkpoint.

A subagent's call to `compact` is refused (its turn ends are not the main
conversation's). A headless (`-p` / SDK) session gets no tool: the engine
has no compactor a plugin can call there yet. The shared session and turn
events are taken with matchers (`isInteractive: true`, `trigger: /^/`,
`reason: "answer"`, the plugin's own origin on `prompt.submit`) because
kairos, agents, appeal and interim register them too,
and the engine admits one
unmatched registration of an event per module.

The tool is an MCP tool to the engine, which tool search defers (the model
sees the name alone until it loads the tool with `ToolSearch`). A
`tool.describe` hook answers `isDeferred: false`, which the engine takes
over its own placement (SPEC 14.4.2, since 2.1.287), so it ships inline in
every request: the definition (about 2.3k characters) in the
prompt-cache prefix, where `/context` counts it under "MCP tools". The
7.202.0 release let it be deferred (2026-10-20), the offer sending the
model to load it; the owner ruled it back inline (2026-10-21), since the
guidance on when to compact has to be in view before any offer comes, and
below the floor, where none comes, at all. Appeal stays deferred. Its
answer is a line.

Known limits: the threshold is read once, at session start, so a window
changed by `/autocompact` mid-session is not followed; a model that keeps
working after the tool answered is compacted at whatever answered turn end
comes; the `resume` prompt enters under the plugin's name, as any
plugin-submitted prompt does; an offer is a turn of its own, a model call
over the whole context (a prompt-cache read, mostly), the price of a
decision at the turn's end, and a turn's settings hooks (its `Stop`
among them) run for it as for any turn; in
a session the person watches in the terminal, the offer and the decline
line show under the answer. An offer overtaken by a compaction still
costs its turn, a short one the model ends with "Not compacting.". Live
check: `tests/mods/live-compact-offer-check.py` (spends model calls; run
by hand).

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
and adds one `context` line telling the model it may appeal once, that the
tool's description says when an appeal fits, and the `select:` query that
loads it (the tool waits behind tool search, deferred since 7.202.0 by the
owner's call of 2026-10-20; compact, deferred with it, is inline again). A block
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
`.claude/settings.json` feeds — the answered async asks (the sminos ask
mod's snapshot, read from `$.state` at `{ plugin: 'sminos', key: 'ask' }`,
none where sminos is not loaded: an answer delivered as a tool result's context is not the
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
`hook`, `setting` or `plugin`, no `approver` of `host`, no organization
`ceiling` (and, on an engine before 2.1.307, no `decider`) — so a pass never
overrides a deny rule, a settings ask rule, a classic hook, another plugin's
ask (the engine puts every hook's ask to a person), or a host. Any
`prompt.submit`, and any answer to a question, ends every pass and makes a
judge call in flight no ruling: the ruling was on the conversation as it
was. An answer reaches the model through no prompt, so the mod hooks
`state.set` on the sminos ask's snapshot and ends the passes when its
`answered` count grows past the one read at the session start.

With doperpowers seated outside devcloud (`prependPlugins`), the secrets
guard sits beneath this mod's `tool.call` hook: it restores a handle in the
call's input before the call runs, and answers a refusal it scrubbed or
noted something on as a `{ deny }`, which the mod reads a block out of as it
reads an error result, putting its notice on the deny's text. A pass is keyed
on the input as this mod saw it, the handle form, while the permission check
sees the restored bytes, so a non-relayed grant on a call that carries a
handle leaves no pass and says so in its ruling (`no-pass` in the log): the
re-run is checked as a new call. One appeal per block; a judge call that fails leaves the appeal open
once more. Every event is logged to
`~/.claude/appeals/<session-id>.jsonl` (seeded from the file at start, the
writes chained), and `/appeals` prints the last 30 days — counts, the grants,
and the `autoMode` entries one more model call suggests from them, for the
person to apply by hand; nothing here writes settings.

Tests: `tests/mods/appeal.test.ts`; the live check
`tests/mods/live-appeal-check.py` drives a headless auto-mode session
through a real block, ruling and pass (it spends model calls; run by hand).

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
until the session is idle and runs as a typed command, with no model turn.

The engine keeps such a run's three rows and sends them with the next
request (2.1.302/303): a caveat (`isMeta`) and the command line, both from
the plugin's origin, and the output, a `local_command` notice. With a reload
every time an update lands, that is a caveat, a command line and an output
folded into the person's next prompt each time. No hook can refuse a row the
engine appends (`session.append` refuses only a plugin's own), and the run
raises no `prompt.submit` to drop, so the module's `session.append` hook on
door `command` empties the three instead: the caveat and the command line
known by this plugin's origin, the output as the `local_command` row after
that command line. An emptied row is kept and sent as `(no content)`, which
no screen draws, so the model reads three `(no content)` lines per reload in
place of the run. The output's text reaches the person outside every
request. A reload that says no more than `Reloaded: N plugins · …` is a
toast (`doperpowers: /reload-plugins: Reloaded: …`), which the debug log
keeps too. One that says more (load errors, an unreachable marketplace, an
update not applied) is this plugin's transcript line (`$.ui.log`). A
transcript line is a system row the engine draws through no render hook, so
no view can fold it once drawn and a resume draws it again: the to-human
view once kept the success line out of its report by sending it to the
debug log as it was logged, but a line logged while the full transcript
showed, or one the hook missed, stayed for good (10-21: 39 of 164 reloads
in this machine's sessions). A system row through `$.session.append` would
be drawn only in the transcript view, its level being `info`. This holds when the reload replaces doperpowers itself: the
engine writes the rows once the new module is loaded, and its hook knows
them by origin. A `/reload-plugins` the person types passes whole.
`tests/mods/live-reload-rows-check.py` pins all of it against a real
session (rows, screen, the request the gateway receives), with and without
the hook.

A reload stops no running work: subagents, background shells,
Monitors and the MCP servers of unchanged plugins carry on, and the old
version's cache directory stays marked in use until the process exits. It
does cost the bridge a restart: a reload into a new sminos starts its
module again, which kills the bridge's child and spawns the next, ending
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
module the reload started meanwhile would show the ask open still. The ask is
the sminos plugin's, so the mod reads that from the ask's snapshot
(`{ plugin: 'sminos', key: 'ask' }`'s `isDialogUp`), seeded at the session
start and kept by a `state.set` hook on it (nothing written, as where sminos
is not loaded, reads as no dialog), and follows the main turn itself through
`turn.start` and `turn.complete`. Open async questions and undelivered
answers no longer hold it, since the ask mod keeps them across the reload. An uninstall is not acted on, nor a newly
installed plugin; a copy run from outside the plugin cache (`--plugin-dir`)
is not watched, since the engine watches that folder itself.

Nor does the module reload into a plugin whose dependency is missing,
whoever wrote the records (its own fetch, a new session's auto-update, a
person's `claude plugin update`, none of which need install a dependency a
new version names). On the tick a due reload would fire (a marketplace
update moves the clone and writes no record, so it is read then, not when
the file changed), it reads what the reload would load: a plugin its
marketplace carries by path at its clone's manifest (found through
`known_marketplaces.json`), which changes when that version is not the one
the session runs, whether or not its record moved; any other plugin at the
manifest of its record's install. If a changing plugin's dependency chain
reaches a plugin with no user or managed record, the reload waits, and the
install that brings the dependency writes the file, which fires it. A
plugin whose loaded version already lacked a dependency holds nothing: the
reload leaves it as it was. A reload is one act, so one such plugin holds
every change with it, cua's and ptc's too, which is why the hold is told
once per hold as a toast and a transcript line (`A plugin update is not
applied: to-human@doperpowers would load without sminos@doperpowers, which
is not installed. /plugin install sminos@doperpowers installs it, and the
reload follows.`), as well as in the debug log.

The module also fetches what the engine fetches only at a session's start.
For each marketplace `known_marketplaces.json` marks `autoUpdate` (from
GitHub or a git URL; this machine's are doperpowers, cua, designer and
ptc-tool), one session per machine at a time, at most every 5 minutes,
reads the remote's head with `git ls-remote` (an entry whose URL or ref
begins with `-` is skipped) and compares it with the marketplace clone's.
Where it moved, it runs `claude plugin marketplace update <name>`. Then,
moved or not, it reads the clone's `.claude-plugin/marketplace.json` and the
manifest at each plugin's `source` folder. It runs `claude plugin install
<dep> --scope user` for every plugin the enabled plugins' dependency chains
reach that has no user or managed record (a name without `@<marketplace>`
is of the dependent's), whether or not anything is behind, so a dependency
another actor's update left out is installed too. Then it runs `claude
plugin update <key> --scope user` for each enabled plugin installed from
the marketplace at user scope whose recorded version is not the clone's
(one the clone holds no manifest of, ci-kit's from a URL, only when the head
moved), except one whose dependency chain reaches a dependency that did not
install: that one is held back, with a debug line, and the rest go on, so a
dependency that will not install on this machine stops only the plugins
that need it. Each fetch tries the install again. The watch then reloads
every session on the machine, once: before a marketplace's update and each
install and update the fetch marks that it applies a batch
(`fetch.applying`, beside its lock), afresh before the next marketplace's
look once a batch is under way, and clears the mark at its end; a reload
waits while the mark is younger than 3 minutes (one command's 2-minute
limit and a margin), so a
batch whose writes land more than a period apart is not reloaded at each,
and a session that dies applying holds the machine's reloads no longer
than that. A release that moves mods into a new plugin that another comes
to depend on thus lands whole: the new plugin is installed before anything
reloads, and while it is not, nothing reloads into its dependent.
Each session looks once a minute whether the machine's fetch is due:
`~/.claude/autoreload/fetch.stamp` is older than 5 minutes, and the lock
directory beside it (`fetch.lock`, made with `mkdir`) is free. The lock
serializes this module's sessions only, and the engine takes none: it saves
`installed_plugins.json` and `known_marketplaces.json` by read-modify-write,
and refreshes a marketplace by cloning beside its clone and renaming the new
one in (2.1.283 on; earlier engines pulled into the clone). The fetch finds
work mostly just after the remote moved, which is when the person or the
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
tests/mods/typecheck.sh                              # every plugin's mods and tests, typechecked
```

Typechecking reads the declarations the engine lays in the plugin's
`.claude-plugin/types/` (gitignored) as a session loads it from a folder it
watches, `claude --plugin-dir`; `tests/mods/typecheck.sh --lay` has the
installed engine lay every plugin's headless in a throwaway HOME, as the
`mods-types` gate does.
Their MCP tools are those connected at that load, so a mod's own registered
tool is known once a session has loaded the plugin.

A tree the engine refuses draws the engine's own component instead and the
reason is in the debug log under `ui.render (<Component>)`.
