# mods

Function hooks of the sminos plugin: one module (`register.tsx`, named by
`hooks/hooks.json` under `modules`) that registers the bridge, the backtick guard, the
sheet's band, the ask's band, the question sheet, the ask, the address and the name, in that order. The engine loads it only where
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` is set and ignores it elsewhere; the
shell hooks beside this folder (`smns-record.sh`, `smns-guide.sh`) run
everywhere.

Across plugins, the order is the owner's settings': `prependPlugins` in
`~/.claude/settings.json` names `to-human@doperpowers`, `sminos@doperpowers`
and `doperpowers@doperpowers`, which seats this module outside doperpowers'
and outside every user-tier plugin's, devcloud's secrets guard and cua's
among them, so the bridge sees a call's input with its handles and its
result scrubbed. The plugin declares no dependency: the engine's only
dependency rule puts a dependent outside its dependency and pushes the
depended-upon behind every plugin nobody depends on, so no declaration
gives a standalone plugin the outer place (the design's §4,
`docs/doperpowers/specs/2026-10-19-sminos-plugin-design.md`).

What other plugins read of this one is its contract, `types/sminos.d.ts`:
the ask's snapshot in `$.state` (`{ plugin: 'sminos', key: 'ask' }`), which
doperpowers' appeal and reload read and observe.

## ask (`ask.tsx`)

Where a session's start chose today's tool (the sheet's start choice,
below), the model asks the human through one tool, `mcp__sminos__AskUserQuestion`:
the built-in AskUserQuestion's questions plus `async`, which is true unless
the call says false (the built-in's `metadata`, an analytics field, is no
parameter of it: a call that passes it is refused as one with any other
unknown key is). A blocking ask (`async` false) is AskUserQuestion: Claude
Code's own dialog opens at once,
with the tab bar across the questions, previews, notes with `n`, "Type
something", "Chat about this" and the review page, and the call returns the
engine's own answer text, byte for byte what the built-in returns for the same
answers. The built-in is withdrawn while the tool exists: it waits behind tool
search, its name alone in the model's view, and a call of it is refused with a
sentence naming the new tool. An async ask (`async` true or absent) returns at once and
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
its `tool.describe` while the session starts, less its "Plan mode note:"
paragraph (through the next blank line; a text without one is left as it
is); what `async` does is the parameter's own description, which says when to
set it false. `$.tool.list()` gives only a tool's first 300 characters, which
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
[ answer ] [ dismiss ]` acts on the oldest, since the ask's own row scrolls
away while the model works. That line is registered before the to-human view, whose band
draws without passing on, so it draws above it; the rows are registered after
the view, which keeps a question in the report.

`[ dismiss ]`, beside every open ask's `[ answer ]`, closes a question gone
stale without a dialog: the row draws `⏺ User dismissed Claude's questions:`,
and the model is told, in the delivery's form, that no answer will come
(`DISMISSED`). That delivery is quiet: it wakes no idle session and never
makes a turn's end submit a prompt, but rides the next route another opens
(the model's next result, the human's next prompt, or a prompt an answer
submits). Nothing for an ask whose dialog is up. The bridge settles the
question withdrawn by `terminal` (by the client, for a dismissal from outside,
below), and a resumed session reads the dismissal
back from the delivery as it reads an answer.

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

The person is told of each ask as the model asks it: the tool's hook raises
`$.ui.notify` with the first question (`(+N more)` when the ask carries
more), a blocking ask's as its dialog is raised, an async ask's as it opens,
and their `Notification` hooks read it as `plugin_notification` before their
notification channel writes. No settings hook hears the model's call itself,
which the tool answers. The dialog the mod raises (a blocking ask's, or the
one a press opens) reaches the PreToolUse and PermissionRequest hooks with
`metadata.source` `sminos-ask` (`DIALOG_SOURCE`), so a hook that announces a
question's dialog can pass over one already announced, or opened by the
person's own press; and while it stands, the engine's reminder that a dialog
has waited (`permission_prompt`, in the generic words it gives an
AskUserQuestion dialog, `DIALOG_REMINDER`) is kept from the `Notification`
hooks beneath (`classic.Notification`), though the channel still writes. A
tool's permission dialog shares those words, so one queued beside the ask's
dialog loses its reminder to the hooks too (the ask has said the session
waits, and the PermissionRequest hooks still hear that dialog); a reminder
that names what waits (network access, a plan) passes. Live
check `tests/mods/live-ask-notify-check.py` (`--from main` runs it against
the code before).

An async ask can also be answered from outside the terminal (`sminos answer`,
later the web): the bridge hands the answers to `answerAsync`, which refuses
one already answered or whose dialog is up, and otherwise delivers them by the
same routes as a press's. It can be dismissed from outside too: the bridge
hands a client's dismissal to `dismissAsync`, which makes the `[ dismiss ]`
press's own dismissal (the same row, the same quiet delivery, nothing counted
as an answer), tells the observer who dismissed it, and refuses, saying why,
where the press does nothing: an ask already answered or dismissed, or whose
dialog is up.

A resumed session rebuilds its async asks from the transcript (the classic
`SessionStart` payload's path). Without a rewind every row of the file is
the conversation. Once the human rewound (the engine records it), only the
conversation the engine resumes counts, rebuilt as the engine rebuilds it:
back from its leaf parent by parent, across a compaction by the boundary's
logical parent, with the rows the engine restores beside that chain (the
results of a response's earlier calls, parented to their own call, and the
attachments under them); a branch the human rewound past, which stays in the
file, is left out. Every call of the tool with `async` not false whose
result is the async one and whose input is valid (a `metadata` it carries,
taken until the tool dropped it, aside) is an ask. The result is what tells
an async call from a blocking one: a call written before `async` defaulted to
true carries no key whether it blocked or not, and a blocking call's result
is the engine's answer or its refusal. An ask reads answered
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
That conversation starts at the last compaction, and each form keeps its
newest 4096 messages, so an ask from before either is not rebuilt in the copy;
the original keeps it. `/branch` writes the copy's transcript whole before the
session starts, and that file is read as a resumed session's is.

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
ends is lost with the process, and its ask reads open on resume (a dismissal
too, which is held until another route opens: dismissed in an idle session
that then ends, the question is open again on resume, and raised again to
the bridge's clients); an async picture reaches the model as a path it has to Read,
and the store is the engine's temp directory, cleaned with old sessions, so a
path delivered long after can be gone; the row reads its answers back from the
engine's text, so a question text that also appears inside an earlier answer
can misplace a row; the lines a search of a transcript over 4 MiB finds carry
no ancestry, so there a branch the human rewound past counts as the
conversation (its asks come back, its deliveries close theirs); and a rewind
inside a running session raises no event a hook sees, so the asks of the
branch it left stay in the row's and the band's view until the session is
resumed.

## sheet (`sheet.tsx`, `sheet-model.tsx`)

The question sheet is the tool's second form. Under it,
`mcp__sminos__AskUserQuestion` puts up to twenty questions on the session's
sheet in one call (the sheet holds up to 500 open) and returns at once; the
agent later revises or withdraws what it asked; the human answers any of
them, in any order, on a surface, and the answers reach the agent as one
message. Design: MAWS's
composite `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`,
child C2; plan `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`,
whose I1 to I13 this section names. What another repository reads (the
record's files, the inbox line, the reader's model, the envelope, the
result's first line) is the published set, `types/sheet/`, frozen: a change
is a ruling of the composite's writer and a new manifest `version`.

**The setting and the start choice.** At its first `session.start` a
process chooses how the session asks, and keeps the choice in `$.state`
(`{plugin: 'sminos', key: 'sheet'}`, `SheetKept` in `types/sminos.d.ts`), so
a reload and a `/clear` keep it: the choice is the process's, made once. In order: a kept choice; a kept `ask`
snapshot and no kept choice (a module before this one served the ask) is
today's tool; `SMNS_INTERNAL` is none; `MAWS_QUESTION_SHEET` of `2:` and this
session's id is the sheet with MAWS as runner (the launch contract MAWS's
C5 sets on the launches it gives the sheet; 2 is the delivery's form,
`MAWS_FORM`: the tool delivers and MAWS rings; any other value, another
session's id as a `claude -p` started inside one inherits it, another form,
or the bare id of no form, is ignored with a debug line saying which);
`MAWS_NATIVE_TO_HUMAN` is
none; a session that is not interactive is none; a record that holds an
open question, a pending outcome (an answer or a dismissal) or a queued
line is the sheet; then
`SMINOS_QUESTION_SHEET` (on for `1`, `true`, `on`, `yes`, off for `0`,
`false`, `off`, `no`, in any case; unset is off, `SHEET_DEFAULT`) with a
surface alive whose reach suits is the sheet; anything else is today's
tool. A surface is a registration under `$SMINOS_HOME/sheet/surfaces/`
(MAWS's daemon writes `mawsd.json`; `tests/sheet_surface.py` is a stand-in),
alive while its heartbeat is at most 30 s old and its pid runs; under
`SSH_CONNECTION` only one of reach `remote` suits. The choice and its
reason are a debug line (`sheet: sheet (terminal): the surface standin is
alive and suits`). Under the sheet the ask yields (`yieldAsk`: no tool, no
band, nothing held; it still draws its own stored calls), the tool is
registered under C1's description (`tests/output-styles/question-sheet/description-v3.md`,
word for word, `DESCRIPTION`) and the published input schema with C1's
field descriptions, and the built-in is withdrawn (`Withdrawn in this
session: ask through mcp__sminos__AskUserQuestion, …`). Otherwise the
sheet's hooks pass everything on and the ask is as above.

**A call.** The input is `{ask, withdraw}`, at least one of them
non-empty and an id at most once across both: `ask` takes 1 to 20 entries (a
question; a header; up to twelve options of a label, a description, a
preview and `recommended`; `multiSelect`; `context`; up to eight
`references` of a path and an optional `[first, last]` line range), an
entry with `id` revising that open question, and the ids to withdraw. The
mod validates the whole call (more than twenty entries, a broken bound, an
empty call or a repeated id: the whole call is refused, as the engine's
error in the words today's tool uses), then each entry alone (unique labels, a preview only on a
single-select question, `multiSelect` only with options, lines in order: an
entry that breaks one is refused alone and the rest apply). Each reference
is read through the engine as the agent's own Read would be
(`$.tool.check`, then on `allow` a `$.tool.call` of Read), so the
permission rules and the other plugins' guards apply, a guard's scrubbing
included; a refused or failed read refuses its entry, and a path outside
the session's working directories is always refused. The call is staged
under `$SMINOS_HOME/sheet/.staging/<session>/<call id>/` and ordered as one
`sminos sheet step`, whose answer is the model's result. Its first line is
`Added q1, q2.`, `Revised q2 (revision 2).`, `Withdrew q3.` (in that
order; when anything in the call was refused, each added or revised id
carries its entry, `q4 (entry 3)`, `q2 (entry 1, revision 2)`, and a
withdrawn id stays bare: `grammar/result.md` in the set), `Nothing done.`,
or `Outcome not known yet.`; a `Not done:` line names each refusal,
and a last line says when no surface can show the questions now. A step
that gives no answer is settled up to three times; if none answers, the
model reads `Outcome not known yet.` and a notice later says what the call
did. A subagent asks on the same sheet, as its asker: only the asker
revises a question, and the asker or the main conversation withdraws it.
A call that adds raises `$.ui.notify` with its first question.

**The record.** One directory a session, `$SMINOS_HOME/sheet/<session>/`
(`state.json`, `inbox.jsonl`, `refs/` for captured bodies, `uploads/`,
`texts/`), its lock beside it; written only by the command (the plan's K1:
a hook can neither lock nor replace a file) and read by every surface. The
mod holds no copy of the sheet: it orders steps and keeps the last view one
answered, adopted in the record's order (`seq`). A surface appends lines to
the inbox through the door (`sminos sheet put`), which tells the session's
bridge (its `sheet` op); a drain applies them: at each start, at the
bridge's nudge, when the bridge's child says hello, at a subagent's stop,
and when a check finds the inbox
grown (one `$.fs.stat` at every tool call, prompt and turn's end the mod
sees, and on a 5 s timer). The record outlives the process: a stopped
session's sheet is read and answered, and what was accepted leaves at its
resume. A `/clear` removes the record it leaves (at `session.end`, again at
the new session's start, and by the daemon's sweep, which a `/clear`'s note
permits but does not guarantee). The mod's removals name the record as it
was witnessed at the clear (`sminos sheet witness`, its identity kept for
every retry) and this process (`--clearing`, its engine's pid): under the
record's lock the command removes that record only, not once it has been
started since (a resume, even one that has stopped again), and not while a
process other than this one runs the session (a resume elsewhere); with neither
known, or either check not answered, the record stays. The daemon's sweep removes a stopped
session's record only once its `state.json` has been unchanged for an hour
and the transcript's own path is confirmed missing, checked again under the
record's lock: any doubt keeps the record.
The command's side is in `skills/sminos/scripts/CLAUDE.md`.

**Delivery** (I9). Each view holds the envelope ready for each recipient:
`[sheet v1] The human answered questions on your sheet.`, a line an answer
(its id, the question, the picked labels, the human's text, `[Image source:
<path>]` for each picture), `Dismissed: …`, and a `<sheet-delivery>` block
the readers read. In a terminal session the main conversation's envelope
goes by the first route that opens: as this plugin's prompt when no main
turn runs and it holds a fresh answer (handed to the engine from a
`$.clock.after(0)` hop, never inside a dispatch; a prompt that enters first
takes it instead); as context on the result of the model's next main-loop
call that returned (not a denied or aborted one, nor a plugin's own call);
or as context on the next prompt that enters (not a slash command). A dismissal, and an
answer given while the session was stopped (marked with its times), start
no turn and leave with whatever route opens next. A large Send leaves in
envelopes of at most 60,000 UTF-16 units and 200 keys, a long text carried
by its head and its file, each but the last saying `More follows.`. A
running subagent's answer goes to it by `$.session.send`, opening with a
line that says it comes from the human; one that ended, or a send not
delivered, goes to the main conversation naming the asker. An envelope
lands when the `session.append` hook finds its block in a row of the
routes' kinds as stored (a `landed` step); one a turn ended without is
looked for in the conversation at the end of the turn it belongs to, and
what is not found is ready again. A start reconciles what an earlier
process may have delivered without recording it: for the keys pending
before the start's drain, it searches the transcript for blocks that landed
(`landedSearchArgs`) and lands those it finds; the rest go again, owed
across a stop. It returns the start's context as the SessionStart's
`additionalContext`: after a
resume or a compaction, the open questions with their options and what is
not yet delivered; in a fork, that its sheet starts empty; then `New ids
continue from q<n>.`. Where the SessionStart came before the choice was
made, or the step (a start's or a compaction's) gave it no context in time,
the context goes instead on the next result or prompt route, once. When the floor can be read (the highest
id the conversation holds, read by `floorSearchArgs`'s perl pass over a
transcript past 4 MiB), a fork's or a lost record's first id is past it. A subagent that stops with questions open is
named to the main conversation once, on the next route.

**A MAWS-run session** (runner `maws`; MAWS's question-sheet C5, F8, F33,
F34). The tool delivers there as in a terminal session by every route but
the idle one: the result and prompt routes carry the main conversation's
envelope, the notices and a context, a route's row lands its keys, a start
searches the transcript, and a running subagent's answer goes by a send.
It submits no prompt of its own (a plugin's prompt carries no context of
its own, and a Stop in MAWS does not withdraw it). When the session is idle
and an answer is owed, MAWS writes its ring instead: a prompt of the
composer's whose whole text is `The human answered questions on your
sheet.` (`RING`). The prompt hook fills a ring with the ready envelope when
that envelope's own block names an answer (`ringHasAnswer`), and otherwise
drops it with `nothing is ready on the sheet` (`RING_DROP`, which MAWS reads)
before taking anything, so a notice or a context that waits still waits; it
awaits nothing first, the engine giving a prompt's hooks ten seconds in all.
The same words under another origin, in a terminal session, or with one
character more are a prompt like any other. The step packs that
conversation's envelope with the batches that hold an answer first (in a
cut batch its answers first), so a ring finds an answer while one is
pending. Each ring's fate is a debug line (`sheet: a ring is filled: …`,
`sheet: a ring is dropped: …`). In both runners a main turn that ends
aborted (a Stop) puts what was then pending for the main conversation in
`noIdle`, and so does the view of a step ordered before that Stop that
answers after it: none of it opens the idle route until a newer answer, and
any prompt that enters carries it all.

**The terminal's drawing** (§8.3 of the composite). `registerSheetBand`,
registered outside the ask's band, draws one line above the to-human band in
a terminal session whose start has answered, while it has open questions or
answers owed across a stop, and not while a survey holds the band: `3
open questions · <surface url>/s/<session> · 2 answers go with your next
message`, or `the page is unreachable: sminos sheet show <first 8>` when
no surface suits. Between steps it refreshes the link from the
registrations' heartbeats alone (every third tick); a step's view is the
full rule. A call of the sheet's form draws, in every session, the
engine's head and one line a question it added or revised (`q7 Auth method
— <the question's first sentence ending in "?", else its first sentence>`)
and one a withdrawal; each line becomes its receipt once the question left
the sheet (`→ OAuth`, `· Dismissed`, `· Withdrawn`, `· Revised below`),
read from the view, else from the delivery blocks the conversation holds.

**Today's asks, moved.** A resume's open asks of today's tool move onto the
sheet once, at the first start under the sheet: the start reads them as the
ask does (`readTodayAsks`) and the step imports each question as it was
asked, marked `importedFrom`, and says so in its context. A read that was
not definite (the search failed or was cut) imports nothing and the next
start reads again; so does a definite read when the floor is not known and
the record has assigned no id (`nextId` 1), since its ids could repeat the
conversation's; a copy's first start under the sheet records that it
never imports.

**The other readers** (§11). Under the sheet the mod writes the `ask` key
of `$.state` the ask writes elsewhere, still `shape: 2`, so doperpowers'
appeal and reload read it unchanged: the 32 questions answered last as
answered asks (`sheet:<id>`, the answer as the envelope words it), the
count of answered questions as `answered` (a dismissal is none), the open
ones and what is owed under `sheet`. Each question and its closing reach
the project's log as a `question` and an `answered` event (`src`
`sheet:<session>:<id>`), projected from the record by `sminos sheet log`,
which the mod orders after a step that owes it, the Stop hook's `sminos
record` runs, and a removal runs, closing what was still open (`removed
with its sheet`).

**The command's verbs** (`sminos help`; a stopped session's sheet too,
named by its member or `--session <id>`; where no member matches, also by
the first eight or more characters of its id when exactly one record's
session begins with them):

    sminos sheet show <who> [--json]           # the open questions, each by its handle (q7, q7@2 after a revise)
    sminos sheet answer <who> q7@2 --pick 1 --text "…" [--image F]   # a bare q7 only at revision 1
    sminos sheet dismiss <who> q8 q9           # one batch
    sminos sheet retract <who> <key>           # a line not yet applied
    sminos sheet remove <who>                  # a stopped session's sheet
    sminos sheet surfaces [--json]             # the registrations, and which are alive
    sminos sheet put <who>                     # the door: JSON lines on stdin

`answer`, `dismiss`, `retract` and `put` append, then (unless `put
--no-wait`) ask the running session for a verdict and print each line's
state once: its verdict (`applied`, `stale` with the current revision,
`closed`, `retracted`, `too-late`), or `queued` when this invocation got
none (a stopped session, no answer in time). `queued` says nothing more:
the line may be applied already, and the printed reply never changes;
`show --json` (`--keys k,…` for some lines) reads its state now. They exit
0 once appended, whatever the verdict; 2 for a line refused before anything
was appended (an `answer` naming a revision no longer current is refused
there, at once, where a line `put` at an old revision is appended and reads
`stale`), 3 for no sheet, 75 for a sheet busy past 10 s (try again), 1 for
a write the file refused. `show` exits 3 for no sheet and 75 when the
record kept changing under its three reads (read again). The exits are
stated in `skills/sminos/scripts/CLAUDE.md`. A session cannot answer, dismiss or
retract on its own sheet. `step`, `probe` and `log` are the tool's own.

Known limits (`docs/doperpowers/TECH-DEBT.md`, rows 37 to 59): a door
killed inside its write can leave part of a batch, which the resend
completes, and the parts may reach the agent in two envelopes; a session
resumed in two terminals delivers what is pending in both; a row is taken
as a landing by what the engine says of it and, where it says nothing of
authorship, by its form, so a tool's output that carries a route's exact
framing and a block with pending keys lands them; a reload between handing
an envelope over and its landing can deliver it twice; across a process
death an answer sent to a subagent can also reach the main conversation; a
captured file enters the session's read state, so after a compaction the
engine attaches it to the model's context as a file the model read; a
rewind past a delivered envelope leaves the answer delivered on the record
and gone from the conversation; a notice that misses every route waits for
the next tool result or a prompt from another origin; where the host's perl
lacks JSON::XS, a very long history's floor search can outlast the step's
20 s, and the import waits for a later start; and a record made again for a
session whose floor is not known starts at q1, so the log keeps the first
`q1`'s question line and drops the new one.

`sheet-model.tsx` holds what takes no `$` (the schema and its validation,
the start choice, the result texts and their parser, the floor, the block's
parser and the rows that land one, the notices, the band's and the row's
lines, the snapshot); `sheet.tsx` the hooks. Tests
`tests/mods/sheet-model.test.ts`, `tests/mods/sheet.test.ts`,
`tests/mods/sheet-delivery.test.ts`, `tests/mods/sheet-drawing.test.ts` (on
`tests/mods/sheet-harness.ts`) and `tests/mods/test-sheet-step.sh` against
the real step; live check `tests/mods/live-sheet-check.py` (it spends model
calls; `--guard-plugin <dir>` loads the owner's secrets guard for its
`secret` case).

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
first in `register.tsx`, so its hooks are the plugin's outermost, and the
plugin is seated outside every other but to-human (`prependPlugins`, above):
what it reports is what the session showed and kept, after every other mod. Never in a session
with `SMNS_INTERNAL` set (derive's headless fork).

`bridge.tsx` holds the hooks and the code that takes `$`: the session start,
the child and the session it serves, control, the wait for a decision, and
the reads of which secrets guard is loaded. The rest sits beside it in
modules that take no `$`, each importing only the ones listed before it:
`bridge-place.tsx` (the rule that judges the bridge's place among the
guards), `bridge-state.tsx` (the one state object, its types,
and `resetBridge`), `bridge-stream.tsx` (the mod's copy of the live state and
the poster), `bridge-requests.tsx` (requests from outside and their
settlement), and `bridge-rows.tsx` (each kept row's notice, a compaction's
rows read from the transcript, and the export to the host).

- **Its place among the guards.** Placement is what keeps the bridge outside
  the guards; this check turns a misplaced bridge off rather than let it
  stream what a guard restored. After every `tool.call` and
  `session.append` settles, the bridge reads `next.trace`, the plugins
  beneath its hook. If the guard loaded now is not among them, the bridge is
  inside it. devcloud's guard counts as loaded when its marker reads live
  (the answer at state version 0). Otherwise cua's copy counts when the user
  settings enable `cua@cua` (the managed settings' seat of cua, for a
  bridge the organization seats in `prepend`; below). A dispatch that lacks the loaded guard's link
  says `off` only when its trace reaches the engine and the guard's own
  plugin did not raise it: a trace cut short (a link answered the call
  itself) still says `safe` when it names the guard or no guard is loaded,
  and otherwise settles nothing; so does a read that fails, said once as a
  toast. Until the first verdict, tool events wait in the post queue with
  everything behind them, and a permission's input is left to the terminal
  (a native question is raised). `safe` posts what waited. `off` drops it,
  stops the child, and raises nothing, questions included; a toast and a
  debug line opening `sminos: the bridge is off` name the `prependPlugins`
  setting. The live state is still kept, and a later dispatch that began
  after the off and sees a loaded guard beneath the bridge (never the reads'
  "no guard" alone, since cua's leg reads the settings' intent) turns it
  back on, toasting so: a new child, as a reload starts one, with a nonce of
  its own, whose hello resyncs it. A guard truly removed leaves the bridge
  off until sminos reloads. Nothing else starts a child while off, a
  `/clear` included. A dispatch that began before the last transition and
  reads `off` changes nothing and posts nothing of its own.
  Off is not final because the trace and the reads are taken at different
  moments, and cua's leg reads the settings' intent: a guard enabled before
  its module loads, or one loaded while a call was in flight, reads `off`
  until the reload that seats it beneath. The check runs on every dispatch
  because `/reload-plugins` replaces only the modules that changed: a guard
  enabled mid-session can load outside a bridge that lives on, or inside it.
  A row's notice goes out before its dispatch is judged, so the reads never
  reorder the notices; a guard has scrubbed the row whichever side of the
  bridge it sits. One window stays open, and is accepted: a call
  whose input is posted before its own dispatch settles, right after a
  guard loaded outside the bridge with no row appended in between. It needs
  an unplaced machine.
- **Its seat.** Whose plugin sminos is, and in which tier, decides how it
  reads the guards. It learns its tier once per module instance from a
  call to its own `state.get` hook (`next.origin.tier` there is the
  plugin's own), and, outside `user`, reads the managed settings: on a
  machine that has them, `prepend` and `append` are theirs alone and every
  plugin a person enables loads in `user`. A person's sminos reads as
  above. Seated by the organization in `prepend`, it is outside every
  plugin a person installs, and a person's devcloud does not hear its
  marker read: no guard of a person's turns it off, and a guard the
  organization seats ahead of it is judged as above: a cua counts where
  the managed settings enable it and declare its marketplace (ids
  case-folded), and a `cua` link beneath it is a guard beneath it. cua's
  missing link decides only on the dispatches that run a person's hooks;
  one an organization's mod raised drops its own call and result and
  leaves the place as it was. Seated by the
  organization anywhere else, it is inside every plugin a person installs
  and cannot read a person's devcloud, so it turns off at its first check
  unless both guards are beneath it. Either way its off line names the
  managed settings' `prependPlugins`. `CLAUDE.md` beside this file lists
  what this does not cover.
- **The stream.** Each chunk of every model request, the main loop's and
  every subagent's (tagged with its turn, loop and index), tool calls and
  results, turns, subagents, usage, a heartbeat (the turn's state, and the
  permission mode the engine last reported), and the requests below.
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
  to the background, then appends user rows telling the model so (a
  plugin's abort leaves no marker of its own, and the moved call's result
  says it runs on), and a row with the reply the abort cut off (a plugin's
  abort drops the text still streaming, which Esc keeps), holding the turn's Bash calls until the row is in, since
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
  the ask mod's external path (`answerAsync`), or dismissed through it
  (`dismissAsync`, below). Each ends with one `settled` naming
  the side whose answer the engine used, read from the engine's
  `tool_decision` record of the call (raised to the mod through
  `telemetry.log`), else the transcript's mark of a hook's decision.
  A permission is raised with its call as the bridge's own `tool.call` hook
  was handed it, never the input the engine's check and dialog hold: those
  come after every `tool.call` hook beneath, where devcloud's secrets guard
  restores its handles to the values, and an allow hands an input back to
  the engine alone, so the values stay on the machine and the request's
  digest is over the handle form end to end. That holds with sminos seated
  outside devcloud (`prependPlugins`). Seated inside it, the bridge would be
  handed the restored call, so the check above turns it off. A permission for a call
  the bridge did not see stays the terminal's, as does one raised before the
  bridge knows its place. A question is raised as
  the engine gave it (the ask mod widens its dialog's beneath the bridge).
  An allow carries an input only where the engine takes none without one:
  a question's, its questions with the answers; `ExitPlanMode`'s, the
  hook's own input, whole (the raised copy is capped, and a cut plan would
  be approved and saved). Any other goes bare: an input, even the call's
  own, has the engine check the call again first, and ask again one an ask
  rule or a safety check put to the dialog.
  The engine's `permission_suggestions` (a rule, a directory, a mode) are
  made from its own input, after the hooks beneath, so a Bash rule can
  carry the whole restored command: a permission carries them (`raised`'s
  `suggestions`, verbatim) only when that input is exactly, whole, the call
  the bridge's `tool.call` hook saw, and only within the bound the hub
  admits (at most 8, each at most 2,048 bytes of canonical UTF-8 JSON); past
  it the request is raised without them. An allow from outside may add
  rules (`updatedPermissions`: the daemon resolves one of those suggestions,
  never a rule a client wrote), still with no input but a question's or a
  plan's; measured on 2.1.310, such an allow on a call an ask rule put to
  the dialog adds the rule and runs the call.
  An async question is answered or dismissed, never denied. Its dismissal
  is the decision `{behavior: "dismiss", by}` on `POST
  /requests/<id>/decision`, with no message, answers or rules: what the
  terminal's own `[ dismiss ]` does, asked by a client. The child relays it
  to the mod as op `dismiss` (`{request, by}`, answered `{dismissed: true}`),
  the ask mod closes the question, and it settles `withdrawn` by that `by`
  (winner `web` for a member, `other` for `cli`), where the terminal's own
  settles by `terminal`. The answers: 200 `{accepted: true, request}`; 409
  with `settled` for a question already settled, however it ended; 404 for a
  request the session does not hold; 400 for one that is not an async
  question (a question in the dialog is declined with a deny, a permission
  allowed or denied) or for a body that carries more; 409 with the ask mod's
  reason when the terminal has the question's dialog up, the question left
  pending; the route's other refusals as for any decision (`lane-b`,
  `launch`, a 504 when the session did not answer in 5 s). A client tells a
  bridge that carries it from one that does not by `GET /status`:
  `capabilities.controls["decide.dismiss"]` is `{available: true}` (an
  observer's `{available: false, reason}`; a bridge from before the
  dismissal names no such key), and `capabilities.ops` lists `dismiss`.
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
loop, twice (commit, then pr), and each ask of the CLI is a Python start: the
mod keeps the line and asks the CLI again only for a new session id (a
session sent to the background goes on as a new one; a module loaded afresh
holds none), after a compaction, or once the kept line is ten minutes old
(an alias renamed mid-session, a `sminos join`); no line (none yet, or a CLI
that cannot run, which keeps the line it had) is asked for again a minute
on. A request waits only for a session's first line: one past its time is
used while the CLI is asked in the background. No file's change stands in
for the ten minutes: what the line is composed from (the engine's record of
the session, the session's own log file, the project's log, the transcript)
is rewritten at every turn or message for reasons of its own, so watching
it would ask about once a turn. A subagent's request reads the
parent's session id, so a subagent's commits carry the session someone can
reach. The engine re-sends its reminder only when the text changes.

## name (`name.tsx`)

A session with a generated name is renamed after what it is in charge of
(`docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md`).
`sminos derive` proposes the name with the session's in-charge line and,
when the engine name it replaces is still the session's, hands it over as a
pending file, `<sminos home>/names/<session>.json`. The mod applies it with
the engine's own `/rename`, `$.command.run({ command: 'rename', args })`,
between turns: every 15 s a timer reads the file, and at the first tick
that finds no main turn running and no ask's dialog up (the ask mod's own
state, read synchronously) it runs the check and then the command. The
engine registers the name as any `/rename` (`user`), writes the transcript's
`custom-title` and `agent-name`, and tells the model itself (a meta row, or
in an SDK session the command's own rows), so the mod adds nothing. The
command starts no model turn. Interactive sessions, `--bg` jobs and SDK
sessions all take it while idle (measured on 2.1.306), so the timer runs in
every session but an internal fork (`SMNS_INTERNAL`), which reads nothing.
The session id is read at each tick, so after a `/clear` the new session's
file is the one read.

The CLI owns the check, `sminos name-due --session <id>`: the name is due
when the session's running engine record still holds the name the file
replaces (no owner's `/rename`, no resume under a new name since), the
session is still one sminos may name, its record does not hold the name
already, and the name is still free in the project and on the machine. The
mod runs it once per pending file's text, whatever comes of it (a CLI that
hangs or fails is not tried again: the next derive rewrites the file, and
that is the retry), so a tick with nothing new pays one failed read. The
one exception is an attempt something overtook: the tick takes the turn
count and the count of ended sessions before its first await, and after its
last await (the session id, read again) judges, with nothing awaited until
the command, a dialog up, a main turn running or started, a session ended
(a `/clear`, a resume) and the id moved; any of them drops the answer and
leaves the file for the next idle tick. A command the engine refuses goes
to the debug log.
`sminos/tests/mods/live-name-check.py` pins the engine facts it rests on.

## backtick guard (`backticks.tsx`)

A Bash call that would hand `sminos` a live backtick is refused before it
runs (`tool.call` on Bash, `{ deny }`). Inside double quotes, or bare, the
shell runs the text between backticks as a command on this machine and puts
its output, or nothing, in its place: a message quoting code arrives changed,
and the code ran. The reason names the span the shell would have run and the
form that carries any text verbatim, `-` with a quoted heredoc
(`sminos say - <<'EOF'`).

The command is lexed as a shell reads it: quotes, escapes, comments, `$(…)`,
`${…}`, heredocs and their delimiters, here-strings, lists and pipelines. Live
is a backtick in a word after the sminos word of its simple command, or in
the body of an unquoted-delimiter heredoc or a here-string on that command or
on one piped into it. Single quotes, `$'…'`, an escaped backtick, a quoted
delimiter's body and a comment are not live, and the inside of `$(…)` is
opaque, since sessions interpolate on purpose. A sminos call is a word whose
last path part is `sminos` or `sminos.py`, as the command or followed by one
of the CLI's verbs, so a call reached through another command
(`devcloud vm ssh box -- sminos say "…"`) counts, and a mention inside
another command's string or heredoc does not. A heredoc's delimiter takes
quote removal alone (`$END` is literal, `$'EOF'` quoted), and an unquoted
body's lines are joined at a backslash-newline before its terminator is
looked for, as both shells do; a sminos call in a substitution inside an
unquoted heredoc body (another command's included) is judged like any
other. A refusal is only ever over a backtick, so a command holding no
backtick, or no `sminos`, is not lexed at all: almost every sminos call.
Where the lexer meets syntax it does not model (a `case` inside `$(…)`, a
`$"…"` delimiter, which bash and zsh read apart, a delimiter holding a
backtick or a `$(`, a substitution that never closes) or spends its work
bound (32 steps a character, at least 4,096, each primitive charged for
the characters it reads), it gives up and the call runs: a miss leaves the shell's behaviour as
it was, a wrong refusal stops a session's work. The guard has no `.catch`:
one that throws is skipped and the call runs too. Registered right after the bridge, inside it, so the
bridge reports the refusal as the session saw it (a denied call's trace
gives the bridge's place rule no verdict). Tests `tests/mods/backticks.test.ts`.

## Developing

```
claude --plugin-dir sminos --debug                      # the plugin from this checkout, hot reload on save
claude plugin validate sminos/.claude-plugin/plugin.json
sminos/tests/mods/run.sh                                # the mods' tests, then the ask's search and the sheet's step run for real
bash sminos/tests/run-sminos-tests.sh                   # the CLI's suite, the shell hooks' among it
tests/mods/typecheck.sh                                 # every plugin's mods and tests, typechecked (from the repository root)
```

Typechecking reads the declarations the engine lays in the plugin's
`.claude-plugin/types/` (gitignored) as a session loads it from a folder it
watches, `claude --plugin-dir`; `tests/mods/typecheck.sh --lay` has the
installed engine lay every plugin's headless in a throwaway HOME, as the
`mods-types` gate does.
Their MCP tools are those connected at that load, so a mod's own registered
tool is known once a session has loaded the plugin.
