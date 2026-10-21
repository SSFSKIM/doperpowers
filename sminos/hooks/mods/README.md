# mods

Function hooks of the sminos plugin: one module (`register.tsx`, named by
`hooks/hooks.json` under `modules`) that registers the bridge, the ask,
the address and the name, in that order. The engine loads it only where
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

The model asks the human through one tool, `mcp__sminos__AskUserQuestion`:
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
  settings enable `cua@cua`. A dispatch that lacks the loaded guard's link
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
  A permission is raised with its call as the bridge's own `tool.call` hook
  was handed it, never the input the engine's check and dialog hold: those
  come after every `tool.call` hook beneath, where devcloud's secrets guard
  restores its handles to the values, and an allow hands no input back, so
  the values stay on the machine and the request's digest is over the handle
  form end to end. That holds with sminos seated outside devcloud
  (`prependPlugins`). Seated inside it, the bridge would be handed the
  restored call, so the check above turns it off. A permission for a call
  the bridge did not see stays the terminal's, as does one raised before the
  bridge knows its place. A question is raised as
  the engine gave it (the ask mod widens its dialog's beneath the bridge).
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
loop, twice (commit, then pr): the mod keeps the line and asks the CLI again
only for a new session id (a session sent to the background goes on as a new
one) or once the kept line is a minute old (an alias renamed mid-session); a
CLI that cannot run keeps the line it had. A subagent's request reads the
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

## Developing

```
claude --plugin-dir sminos --debug                      # the plugin from this checkout, hot reload on save
claude plugin validate sminos/.claude-plugin/plugin.json
sminos/tests/mods/run.sh                                # the mods' tests, then the ask's search run for real
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
