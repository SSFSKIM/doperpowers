# Fold summaries: what a fold of working record says before it is opened

Under the `to-human` output style the person reads a session as a report: the
messages the session sends them, with everything else (tool calls, results,
unsent notes, deliveries from subagents and other sessions) folded behind one
button per stretch. Today every such button reads `› working record`, which
says nothing: to learn what a stretch held, or what the session is doing right
now, the person has to open it. After this change the button says it. A fold
that is still growing reads its newest tool call in one line
(`› Listing the U3a document's headings and read observation O-41's lines`),
and a fold that has closed reads a one-line summary of the stretch
(`› Reviewed ci-kit #67: found a spaced-path bug in job cleanup, sent back for fix`),
written by Haiku 5.5 from that stretch alone. To see it working: run a
to-human session in a terminal, give it work that takes several tool calls,
and watch the button under the last message change with each call, then
settle into a summary a few seconds after the next message arrives.

The human partner approved this design on 2026-11-12, choosing: one line on
the button for the live fold, Haiku at high effort over the run alone (not a
fork of the session), the plain wording, Claude Code's own view only, and no
summaries for folds that closed before the feature was installed.

## Progress

- [x] (2026-11-13 00:24Z) Design approved; spec written.
- [ ] PR #499 merged to `main` (a subagent's rows stand in no run of the main
      conversation). As of 2026-11-13 01:04Z: CI green on `5ffc7690`; its second review
      found two defects in its start-up scan, with its author for a fix; a
      follow-up probe may replace the scan. M1 does not wait for it ("What
      this builds on").
- [x] (2026-11-13 00:34Z) Spec review and execution-section review absorbed (eight findings, six distinct, all taken; Decision Log).
- [ ] M1 — the run tracker and the live line.
- [ ] M2 — summaries, storage, the live check, docs.
- [ ] Whole-branch review (`doperpowers:reviewer-medium`), retrospective, merge.

## Terms

- **Row**: one entry of the main conversation as the engine keeps it (a
  `session.append`), or its drawing in the transcript (a `ui.render`). A tool
  call's drawn row is known by the call's `tool_use_id`; any other row by its
  `uuid`.
- **Read row**: a row the person reads in the report. The view
  (`to-human/hooks/mods/to-human.tsx`) keeps these visible: a message sent
  through `mcp__to-human__message` or carried in a `<message>` mark, an agent
  spawn (`Agent`, `Workflow`), a question (`AskUserQuestion` or the ask mod's
  tools), the person's own prompt, an API error, the failure notification of a
  spawn it shows.
- **Record row**: every other row: a tool call and its result, an unmarked
  assistant text (a **note**), a delivery (a background task's notification,
  another session's or a subagent's message, a plugin's prompt).
- **Run**: the record rows between two read rows. The view draws one button
  for a run: its **fold**.
- **Open run**: the run after the last read row, which later rows may still
  join. Every other run is **closed**.
- **Live line**: one line naming the newest tool call of a run.
- **Summary**: one line, written by a model, saying what a run did and what it
  came to.
- **Digest**: the text built from a run's rows that the model reads to write
  the summary.
- **Tracker**: the new module that follows the conversation's rows as they are
  kept and holds each run's live line, digest and summary.
- **Place**: a row's position in the transcript, a number the view keeps for
  every row id (`View.place`): the row's index in the transcript file for rows
  the file held when the module loaded, and `LIVE + n` for the n-th row
  appended since.
- **`$.state`**: named values the engine holds for a session on a plugin's
  behalf. They outlive a reload of the plugin's code (module variables do not)
  and end with the process. A drawing that reads one is drawn again when it is
  written. sminos keeps its ask mod's state there (`sminos/types/sminos.d.ts`).

## What the person sees

The fold's button keeps its form (the dim `›` control the view draws through
`control(...)`, pressed to unfold, `‹ fold to report` to fold back). Only its
text changes. A run is **live** from the moment a row joins it until its
summary has come back, failed or been skipped:

| The run | The button reads |
|---|---|
| live, with a tool call | `› <live line>` |
| live, no tool call yet | its last summary if it has one, else `› working record` |
| not live, summarized | `› <summary>` |
| not live, no summary (the call failed, the run predates the feature, the tracker did not hold the run whole) | `› working record` |

So a closed fold shows its last call's line for the few seconds its summary
takes (longer when one of its calls is still running as the run closes: "When
a run closes"), then the summary. The engine's own row for the newest call
(description, command, cut output) was the alternative for the live fold; the
human partner chose one line, which keeps the report quiet and the fold one
row high.

### The live line

Built from the call's name and input, since the engine hands a hook those and
not the line it draws, and a button holds only text:

| Tool | Line |
|---|---|
| `Bash` | its `description`; without one, the first line of `command` |
| `Read`, `Edit`, `Write`, `NotebookEdit` | `Read <file name>`, `Edit <file name>`, `Write <file name>`, `Edit <file name>` (the base name of the path) |
| `Grep`, `Glob` | `Search "<pattern>"` |
| `SendMessage` | `Message to <to>: <summary>`, or `Message to <to>` without a summary |
| `Skill` | `Skill <skill>` |
| `ToolSearch` | `Tool search "<query>"` |
| an MCP tool `mcp__<server>__<tool>` | `<server>: <tool>` |
| anything else | the tool's name |

A line is one line: newlines become spaces, and it is cut at 120 characters
with `…`. Several calls in one response: the last one's line.

### The summary

One line in plain words, at most 90 characters asked for and cut at 120 with
`…` (under the final prompt Haiku overran 90 on 5 of 12 test runs, to at most
113). It is written in the language of the session's notes. The exact system
prompt is in "The model call". Three wordings were put to the human partner on
the same 12 real runs (`~/.local/share/fold-labels/labels-compared.md` on the
owner's MacBook): specific (hashes and run ids kept), plain, and a
50-character log line. They chose plain: it drops commit hashes and the
session's own working labels, which mean nothing to someone who did not follow
the work.

One line is kept however long the run, and a line is selective. A 14-call run
that recorded a design decision, checked another PR and relayed a review
finding was labelled by the finding alone; on a 143-call run the three
wordings each named a different thread. What the samples' labels said was in
their records (see Evidence); what they left out is one press away.

## When a run closes

A run closes, and is due a summary, at whichever comes first:

1. A read row is kept after it.
2. The turn ends (`turn.complete` of the main conversation) while the open run
   has taken rows since its last summary.

Rule 2 exists for the stretches where the session ends its turn without
sending anything. In a census of the owner's sessions (Evidence), the person's
next prompt closed 22% of folds: work nobody was told about, where a summary
is worth most. Without rule 2 those would read a stale live line until the
person typed.

The summary is asked for once the run has closed and every call in it has its
result, or at the turn's end if one never comes. A response can hold a call
beside a message or a spawn (`[Bash, message]`): the message closes the run as
it is kept, before the Bash call has run, and the view draws that call's
result inside the earlier fold, at its call. Asked for at the close, the
summary would miss the very result the run was for. Until the result is kept
the run stays live and reads the call's line, which is true: the call is
still running.

A run summarized under rule 2 is still the open run. If a later row joins it
(a notification wakes the session and it works on with no read row between),
the run is live again: the button shows the new calls' lines, and the next
close summarizes the whole run, replacing the earlier summary. A summary that
comes back for a run that has taken rows since it was asked for is discarded.
A run keeps its last summary until a newer one replaces it.

## The tracker

The view cannot supply a run's content or notice its close on its own: it
learns of a row when the row draws, and in a fullscreen terminal rows outside
the window never draw. So a new module, `to-human/hooks/mods/folds.tsx`,
follows every row of the main conversation as the engine keeps it
(`session.append`, `agentId` undefined) and each turn's end (`turn.complete`,
`agentId` undefined). It registers from `registerToHuman`, as `registerEdits`
does, and reads the view's `place` map.

Rebuilding the view's own run logic on kept rows instead of drawn ones was the
larger alternative: it would end the class of bug where a run's bounds depend
on what has drawn. It is a rewrite of a 1,580-line module whose drawn rows do
not map one to one to kept rows (the engine groups calls into one row, and
hands a drawn prompt its sender where a kept one has none), so it is not this
initiative's. The tracker classifies kept rows with the view's own exported
rules, and the two meet only at a row's place.

### What each kept row does

The tracker classifies with the view's exported rules: `isRead(tool)`,
`parse(text)`, `promptRow(props, spawns)`, `isApiError(origin, message)`
(export it), `FINAL_ANSWER`. A kept prompt carries less than its drawing,
though: the engine hands the drawn row `from` (who sent it) and `task` (the
background task it reports on), and `promptRow` leans on both. So one function
of the tracker's rebuilds them from a kept prompt before asking `promptRow`,
for every prompt however it was kept:

- `task`: from a `<task-notification>` body in the text, its `<tool-use-id>`
  and `<status>`.
- `from`: present when the row is a sender's and not the person's typing: its
  origin's kind is `channel` (the engine gives a channel's message a sender,
  and `promptRow` reads a `channel` origin without one as the person's), or
  the row is `isMeta`, the engine's mark on a user-side row the person does
  not see as typed.

`promptRow({ origin, text, task, from }, spawns)` then answers as it does for
the drawing: `record`, a delivery in the open run; `user` or `marked` (the
failure of a spawn the report shows), a read row.

| Row | Effect |
|---|---|
| Assistant text with no mark (`parse(text).spans.length === 0`) | a note in the open run |
| Assistant text with marks | a read row. If `parse(text).hasRecord`, the row is also the first row of the next run and its text that run's first note (the view draws such a message's button on the message itself) |
| A `tool_use` block of a read tool (`isRead`) | a read row; an `Agent` or `Workflow` call's id is remembered as a spawn |
| Any other `tool_use` block | a call in the open run; it sets the live line |
| A tool result | the result of its call, in the run that holds the call, open or closed; a read tool's result is ignored |
| A prompt or a delivery (doors `prompt`, `delivery`), kept between turns or folded into a running turn | its kind by the rule above: a delivery in the open run, or a read row |
| An API error row (`isApiError`) | a read row |
| The response the message mod makes up after a final message (text `FINAL_ANSWER`, no request) | ignored |
| A compaction's rows (door `compaction`) | a read row |
| Anything else (thinking, hook context, notices, commands, other attachments, a row a tool hands over beside its result, a queue record, a subagent's rows) | ignored |

A first row that joins when no run is open starts one.

**A prompt folded into a running turn** is kept, by the diagnosis's probe log
("What this builds on"), through the door `delivery` with its sender's own
origin, right after the tool result it rides: `peer` for a subagent's
hand-back, `task-notification` for a task's. (The engine's reference describes
the kept row, an attachment named `queued_command` holding the engine's
rendering; the event carries the sender.) So it is classified as any prompt
is, and the tracker keeps no memory of the queue: a queue record, door
`queue`, carries the engine as its origin and is ignored. The person's own
prompt typed into a running turn is kept the same way, door `delivery`, origin
`composer`, which `promptRow` reads as theirs.

A message call that sends nothing (refused or errored) is a read row here and
a record row in the view, which learns of the refusal from the result. The
difference moves one summary's boundary, and refused message calls are rare (a
subagent's, an empty one); matching it would mean holding every message call
back until its result.

### What the view reads

The tracker publishes what a fold's button needs in `$.state`, under two keys
of the to-human plugin (the contract is in Interfaces):

- `folds`: the closed runs, oldest first, each with its first and last row
  ids. Written when a run closes and when its summary settles.
- `fold`: the open run, with its first row id. Written when its live line or
  summary changes.

The view reads both where it draws a fold's button and finds the run of the
row that draws it by place: the open run if the row's place is at or after the
open run's first row's, else the closed run whose first and last rows' places
hold it. A row in no run reads `working record`, and so does one whose place,
or whose run's bound's place, the view does not know (`View.place`; a place
the view only guessed for a row drawn before it was kept is not one). A group
of calls is one row the view knows as `group:<its first call's id>`: the
lookup takes the call's id, as the view's `keyOf` does. The label is the run's
live line or summary by the table in "What the person sees".

Finding the run by place is why whichever row happens to draw the button finds
the label (in fullscreen the earliest *drawn* row of a run is not always its
first), and why summaries read back after a resume still attach: the view
reads every row's place from the transcript file at start. Keying a summary by
the run's first row alone fails whenever that row has not drawn; indexing runs
by their first rows alone would hand a row of a run the tracker never saw
(kept while the plugin was off) the label of the run before it.

`$.state` rather than module variables with `$.ui.invalidate('ui.render')`,
the view's usual way: a write draws again only the rows that read the value,
which here are the buttons, where an invalidation asks every mounted row of
the plugin again on every tool call; and the values outlive a reload, which
this owner's sessions go through several times a day.

### The digest

Built as rows arrive, each part cut when it is added:

- `NOTE <text>`, cut at 1,500 characters.
- `CALL <name> …`: for `Bash`, ` — <description>` then a line `$ <command>`
  cut at 600; for a tool with a `file_path`, `path` or `notebook_path` input,
  that path (and ` pattern="<pattern>"` where there is one); otherwise the
  input as JSON cut at 400.
- `RESULT <text>` (`RESULT (error) <text>` for an error), cut to its first 600
  and last 400 characters with the count cut between them: test and build
  output puts its verdict at the end.
- `DELIVERED <text>`, cut at 600.

Parts are joined by blank lines. A digest over 60,000 characters keeps parts
from the start up to 40% of that and parts from the end up to 60%, with one
line between them saying how many rows were left out; the tracker need not
hold what the cap would drop, which bounds its memory on a long run.

These are the shapes and cuts the label test used. On the owner's runs the
median digest was 8,181 characters and 81 of 1,967 runs met the cap. A digest
runs about 2 characters to a token (paths, hashes and JSON are token-dense),
so the cap is about 30k tokens, under the 100k where Haiku 5.5's price steps
up.

### The model call

One call per close, through the session's own client, never awaited by the
hook that noticed the close:

    $.model.complete({
      model,                 // TO_HUMAN_FOLD_MODEL, else 'haiku'
      system: LABEL_SYSTEM,
      prompt: `<stretch>\n${digest}\n</stretch>`,
      effort: 'high',
      maxTokens: 4000,
      timeoutMs: 30_000,
    })

`LABEL_SYSTEM`, exactly:

    You label folded stretches of a coding agent's working record. The person supervising the agent sees your label in place of the stretch and decides from it whether to open the stretch. They have not read the stretch and do not know the names the agent made up while working.

    You are given one stretch: the agent's own notes (NOTE), its tool calls (CALL), their results cut to their ends (RESULT), and messages delivered to it from subagents, jobs or other sessions (DELIVERED).

    Write one line of at most 90 characters, in the past tense with no subject: what was done and what it came to, in plain words. Keep pull request and issue numbers and the counts that matter (tests passed, files changed); leave out commit hashes, run ids and the agent's own working labels, saying what the thing is instead. Write in the language the agent's notes are written in, and in English when there are none. State nothing the record does not show. Answer with the line alone.

The summary is the reply's first non-empty line, trimmed, cut at 120
characters. A reply that is not answered or is empty, or a call that throws,
leaves the run's summary as it was: one attempt, no retry, a line in the debug
log (`$.ui.log(..., { to: 'debug' })`). A fold whose first summary fails reads
`working record`, which is today's behaviour, so a spent quota or a blocked
model costs nothing but the feature.

`TO_HUMAN_FOLD_MODEL` (read once, through `$.env.get`) names another model for
a launch; the live check uses it to make the call fail. `haiku` is an alias
the session resolves as `--model` would, so the owner's gateway mapping
applies.

Why this call and not another:

- **A fork of the session** (`$.model.fork`, the session's own transcript
  read from the prompt cache) was the human partner's first proposal. It has
  the whole context, and costs one read of the whole conversation per fold: on
  the census, $0.053 a fold at a median 253k tokens, $104 over ten days, 3.1%
  of the sessions' spend before the fork's own output. Haiku over the digest
  comes to about $0.0011 a fold (the mean digest is 14,300 characters, about
  7,200 tokens, $0.0007 at $0.10 per million; plus 420 to 730 output tokens,
  $0.0002 to $0.0004 at $0.50 per million): about $2.20 over the same folds.
- **A field on the message tool**, the model writing the label as it sends a
  message, costs no request, but a message closes only 36% of folds (a spawn
  31%, the person's prompt 22%, a question 11%), and it adds an obligation to
  a tool contract MAWS and the desk build on.
- **Effort `high`** is the human partner's call. Output, mostly thinking, is
  about a third of a label's cost; the whole is small enough that a lower
  effort was not tested.

### What the tracker holds whole

The digest's parts are module variables: a reload of the plugin's code (an
update the reload mod applies, `/reload-plugins`) loses them, while the
published runs stay in `$.state`. A module that starts and finds an open run
there takes it up as a run it does not hold whole: its live line goes on
changing with new calls, and it is never summarized again, so it keeps the
summary it had, or none. The next run is whole. Keeping the parts in `$.state`
too would close this gap at the price of rewriting up to 60,000 characters on
every kept row; the human partner declined summaries for folds without one
("only folds that close from now on"), and the same answer covers a run a
reload interrupted.

At start the tracker also clears what the old module left in flight: a closed
run still marked live had a request that died with that module, so it loses
the mark and reads its summary, or `working record`.

### Storage

Summaries are kept past the session so a resume shows the ones already made:
one JSON file per session, `to-human/folds/<session id>.json` under the
configuration directory (`CLAUDE_CONFIG_DIR`, else `$HOME/.claude`), written
whole through `$.fs.write`:

    { shape: 1, runs: [[<first row id>, <last row id>, <summary>], …] }

Every run with a settled summary is in it, the open run among them with the
last row its summary covered, and the file is written each time a summary
settles: a turn that ends without a message is the case rule 2 exists for, and
its summary has to outlive a quit as any other does.

At `session.start`, when `$.state` holds no `folds` yet (a new process), the
tracker publishes its session's file, every run of it as a closed one, and
removes files older than 30 days (one `find … -mtime +30 -delete` through
`$.process.run`: `$.fs` has no delete). A new process did not see the rows of
the run that was open at the quit, so it cannot hold that run whole: rows that
join the same fold after a resume start a run of their own, and the fold goes
on reading the stored summary until a read row is kept. Restoring it as the
open run would let it take those rows' live lines, and would hand its summary
to every later fold if the session had meanwhile run without the plugin.

On a `classic.SessionStart` whose source is `clear`, `resume` or `fork` (the
view resets on the same event) the tracker drops what it published and
publishes the file of the session it now is. A write that fails is logged to
the debug log; the summary stays in `$.state`.

A file per session is how the appeal mod keeps its log
(`hooks/mods/appeal.tsx`: `~/.claude/appeals/<session id>.jsonl`). The
engine's plugin store (`$.store`) was the first choice and lost: it is one
file shared by every session of the plugin on the machine, no plugin here uses
it yet, and the engine's documentation says neither whether two sessions'
writes both survive nor whether the file carries over an installed update (its
name ends in a hash). Settling that takes a probe through a real marketplace
update; a file one session alone writes has nothing to settle.

### Where it runs

The tracker follows rows and publishes live lines in every session the plugin
loads in; that is a few small `$.state` writes. It asks for a summary only
when all of these hold:

- the view has seen a mark (the session writes for a to-human reader: the same
  `hasSeenMark` that turns folding on);
- the session is interactive (`session.start`'s `isInteractive`): nobody reads
  a headless session's terminal;
- `MAWS_NATIVE_TO_HUMAN` is unset or empty: MAWS draws its own report;
- `SMNS_INTERNAL` is unset: a sminos internal fork has no reader.

## Evidence

The census: every main-conversation row of the 13 to-human sessions this
repository's project ran in the ten days to 2026-11-12 (about 36,000 requests,
$3,373 at list prices, Opus 5.5 for nearly all), walked by
`~/.local/share/fold-labels/digest.py` on the owner's MacBook with rules that
approximate the view's. 1,967 folds. Closed by a message 36%, a spawn 31%, the
person's prompt 22%, a question 11%. Median 9 to 12 tool calls for a fold
closed by a message, spawn or question, 4 for one closed by the person's
prompt; 24% of folds hold two calls or fewer.

The label test: 12 of those runs, two from each of six size bands (0 to 143
calls), labelled by `claude-haiku-5-5` at high effort through `label_cli.py`
in the same folder, four times (three wordings, then the chosen wording with
the language rule). Mean time 2.6 to 4.3 s a label. The run whose notes were
Korean came back in Korean under the final prompt, the rest in English. Two
runs were read whole against their labels (digests of 4,932 and 12,582
characters): each label stated only what its record showed, and the longer
one named one of the run's three threads. Through the CLI the test paid about
$0.0022 a label, twice the plain-completion figure above: the CLI writes the
prompt to the one-hour cache at twice the input price, and the sample leans to
large runs.

## Acceptance

Each is checked in a real terminal session under the `doperpowers:to-human`
output style with this branch's plugin loaded; `live-folds-check.py` (M2)
automates 1 to 5.

1. While a turn runs tool calls after a message, the fold under that message
   reads `› ` and the newest call's line: for a Bash call, its description.
2. Within 30 seconds of the message that ends the stretch, the same fold reads
   a one-line summary: not `working record`, and not the last call's line.
3. A turn that runs tool calls and ends without sending a message leaves a
   fold that reads a summary once the turn has ended, before anything is
   typed.
4. After `/reload-plugins`, and after quitting and `claude --resume`, the
   folds summarized before still read their summaries, the fold of item 3
   among them when the quit comes right after its turn.
5. With the model call made to fail (`TO_HUMAN_FOLD_MODEL` set to a model id
   that does not exist), a closed fold reads `› working record`, pressing it
   unfolds the run, and the session is otherwise unaffected.
6. A session without the output style makes no summary call: its debug log
   shows no completion from the to-human plugin, and its transcript draws as
   the engine's.
7. A run during which the session took in prompts mid-turn (a background
   command finishing while another call runs) draws one fold with one summary.

## Execution

### What this builds on

The report that came with this request, one run drawn as many folds back to
back, led to PR #499. Its cause as reproduced: a subagent's transcript, opened
in the fullscreen terminal (the agent picked in the strip under the prompt),
draws through the view's hooks, nothing on the event says whose row it is, and
the view stood those rows in the main conversation's order, where a read row
of the agent's cut a main run in two. With #499 a row the view knows for
another loop's (`View.apart`: an append with `agentId`, or a row of a
subagent's transcript file) draws as the engine draws it and stands in no run.
The tracker ignores a subagent's rows already. Whether this is what the owner
saw is not confirmed (Surprises & Discoveries).

M1 does not wait for #499: the tracker ignores a subagent's rows by their
`agentId` whether or not the view sets them apart, and nothing else here
depends on it. #499 is still changing as M1 starts (its start-up scan has two
open review findings, and a follow-up probe may replace the scan with a
general rule about rows the conversation never kept), and it edits
`to-human.tsx` around `place`, `placeAll`, the `session.append` hook and the
first lines of each render hook. This branch takes `main` when it lands; until
then M1 keeps its own edits to that file to the places "M1" names, so that
merge stays small.

The diagnosis's probe is the source for the tracker's fixtures:
`~/.local/share/fold-runs/probe-runs.py` on the owner's MacBook starts an
isolated haiku session with a probe plugin outermost, which logs every
`session.append` (door, origin, role, blocks) and every `ui.render` (the props
that classify the row); its scenarios are `notify`, `agent`, `view`, `view2`,
`resume` and `compact`, and two logs are kept in `evidence/` beside it. A
fixture the kept logs do not hold is made by running the script with a
scenario added, a few haiku calls each; the scenarios `ghost` and `ghost2`
(logs `queued-prompt-*` and `queued-handback-*`) hold a prompt typed into a
running turn and a hand-back queued behind a message.

### Constraints on every milestone

- The engine's rules for a hooks module, each learned the hard way here: `$`
  is passed only to functions in the same file; a module gets one unmatched
  registration of an event, so a further hook on `session.append`,
  `session.start`, `classic.SessionStart` or `turn.complete` takes a matcher
  (the to-human module's own are in `to-human.tsx`, `message.tsx` and
  `notify.tsx`; `hooks/mods/CLAUDE.md` shows the doperpowers mods'); the
  loader refuses a module that keeps the value of a function it hands `on`; a
  `$.state` reference is a const whose `plugin` and `key` are literals, used
  for nothing but `$.state` calls; a render hook never writes `$.state`.
  `claude plugin validate to-human` reports what the engine would refuse.
- Nothing the tracker does may delay or fail a row's keeping or drawing: its
  hooks call `next(e)` whatever happens inside them, and no hook awaits the
  model call.
- The message tool's contract (name, input, result) and the output style's
  text do not change.
- `to-human/tests/mods/run.sh` and `tests/mods/typecheck.sh` pass at each
  milestone's end. The gates run on GitHub Actions: `ci-gate` from the
  worktree verifies a commit.
- The to-human plugin's version is bumped once on this branch, with
  `scripts/bump-version.sh --plugin to-human <version>`, in the first commit
  that changes a shipped file: to `0.8.0`, or the next minor above `main`'s if
  the bug's fix took a number past `0.7.x`.

### M1 — the run tracker and the live line

At its end a to-human session's live fold reads its newest call's line, the
tracker publishes every run's bounds, and no model call is made anywhere.

Touches: `to-human/hooks/mods/folds.tsx` (new), `to-human/types/to-human.d.ts`
(new, the `$.state` contract) and `to-human/.claude-plugin/plugin.json` (its
`types` key, as sminos' names `./types/sminos.d.ts`),
`to-human/hooks/mods/to-human.tsx` (the two places a fold's button is drawn,
`recordRow` and the mixed message's button; the export of `isApiError`; the
registration beside `registerEdits`), `to-human/tests/mods/folds.test.ts`
(new), `to-human/tests/mods/to-human.test.ts`, whatever
`tests/mods/typecheck.sh` needs to see the contract, and every live check
that stages the to-human plugin (`live-message-check.py` and
`live-resume-check.py` copy `.claude-plugin` and `hooks` for it by a `PLUGINS`
list, and `live-final-check.py` stages it likewise): each must copy `types`
too, or its staged manifest names a contract that was not copied.

Exposes: the `$.state` contract, `registerFolds`, `labelOf`, `lineOf`
(Interfaces).

Decisions that are this milestone's:

- The kept logs hold no failed spawn's notification (none could be provoked
  cheaply): build that fixture from the engine's types and `promptRow`'s rule
  for it, kept between turns and folded into a running turn.
- Keep the classification, the live line and the lookup as pure exported
  functions the tests call without an engine; the hooks are thin.
- Tests that press a fold find the button by the text `working record` today;
  they keep passing for runs with no call, and the new tests press by the
  label the run should carry.

Does not touch: the model call, the digest, the summaries' file, the docs.

Proves: acceptance 1 and 7 (7's "one fold"; its "one summary" is M2's), by
unit tests that pin: each row of "What each kept row does" has its effect,
from fixtures the probe log supplies where it has them and the engine's types
where it does not (no channel is configured on the owner's machines): a
prompt as the person's, as a delivery, as a channel's message, and as the
failure of a shown spawn, each kept between turns and folded into a running
turn; a result kept after its run closed joins that run; blocks of one response are taken
in order; the live line of each tool in the table, cut and flattened; a label
found from any row of its run, of the open run and of a closed one, a group's
row among them, and from no row outside them or without a known place; a live run with no call reads its summary or nothing; a
subagent's rows change nothing; a module that starts over an open run in
`$.state` goes on with its live line.

### M2 — summaries

At its end a closed fold reads its summary, a turn's end summarizes the open
run, summaries outlive a reload and a resume, and the public docs say so.

Touches: `to-human/hooks/mods/folds.tsx`, `to-human/tests/mods/folds.test.ts`,
`to-human/tests/mods/live-folds-check.py` (new, beside the other live checks,
which show the isolated launch: a temporary config directory, the worktree's
plugins by `--plugin-dir`, a tmux pane, Haiku through the gateway keys in the
environment; it stages `types` with the plugin), `to-human/CLAUDE.md` (a
paragraph for `folds.tsx`; the sentences
that say a run folds behind `› working record`), `to-human/hooks/hooks.json`
(its description), `docs/whats-inside.md` (the report view's row),
`hooks/mods/README.md` (the to-human section's lines on the button),
`tests/CLAUDE.md` (where the live checks are listed).

Consumes: M1's tracker and contract. Exposes `LABEL_SYSTEM`.

Decisions that are this milestone's:

- The tracker's own memory is the authority for the runs. `$.state` and the
  session's file are written from it, whole, each through one chain of writes so
  they land in order (`keepOpen` in `sminos/hooks/mods/bridge-btw.tsx` is the
  pattern), and nothing reads them back after start: a `$.state.get` made in a
  hook reads the moment of that hook's dispatch, whatever was written since.
  A reply merges into memory by its run, so replies for different runs settle
  in any order.
- A summary request carries the session's epoch (bumped on a `clear`, `resume`
  or `fork`, which change the session without loading the module again), its
  run, and the run's generation (bumped whenever a row or a result joins the
  run). A reply whose epoch or generation is no longer current is dropped, and
  writes nothing to `$.state` or to any session's file.
- The live check is run by hand, like its siblings (it spends Haiku calls, so
  no CI gate runs it); say so in its header.

Does not touch: the view's run logic, the message tool, sminos, MAWS.

Proves: acceptance 2 to 6, and 7's "one summary". Unit tests pin: a close at
each kind of read row asks once, with the digest of exactly that run; a run
closed while one of its calls runs is asked for when that result is kept, with
the result in its digest, and at the turn's end if it never is; two runs'
replies settling in the reverse order leave both summaries in `$.state` and in
the session's file; a reply held across a `clear`, a `resume` and a `fork` and
then released changes neither `$.state` nor either session's file; a turn's
end asks for the open run, a later row makes it live again, the next close
asks for the whole run, and a late reply for the earlier generation changes
nothing; a turn's end with nothing new asks nothing; the digest's parts, cuts
and cap; the summary's first-line and 120-character rules; unanswered, empty
and thrown calls leave the summary as it was; no call before a mark, when not
interactive, under MAWS, under `SMNS_INTERNAL`; a run not held whole is never
asked for; a closed run left live by an old module loses the mark at start;
the file's shape, a turn-end summary of the open run in it, its publication
into an empty `$.state` as closed runs, the prune's command, the reset on
`clear`, `resume` and `fork`; a failed write keeps the summary. Then the acceptance section as written.

### Concrete Steps

From the worktree's root.

    to-human/tests/mods/run.sh          # every *.test.ts under to-human/, then session-places.ts; ends with the kit's pass count and exit 0
    tests/mods/typecheck.sh             # tsc over every plugin's mods and tests; no output and exit 0
    claude plugin validate to-human     # lists the module's hooks, calls and state keys; no refusal
    scripts/bump-version.sh --since origin/main   # exit 0 once to-human's version is above main's
    ci-gate                             # the repo's gates on the committed HEAD; ends GREEN <run-url>

M2's live check, by hand, with the gateway keys in the environment as the
sibling checks' headers describe:

    to-human/tests/mods/live-folds-check.py [--keep]

It starts one isolated session and prints one line per acceptance item it
automates (1 to 5; for 4, a reload after item 2 and a quit and resume right
after item 3's turn) with PASS or FAIL and the pane text it judged. Items 6
and 7 are checked in the same kind of session by hand, or added to the script
where that is cheap; record which in Progress.

### Interfaces and Dependencies

In `to-human/types/to-human.d.ts`, the plugin's `$.state` contract (declared
under the plugin's name in `PluginState`, as `sminos/types/sminos.d.ts` does):

    /** One run of working record as the tracker publishes it. */
    export type FoldRun = {
      /** The run's first row; a tool call's row by its call's id. */
      first: string
      /** Its last row, once the run is closed. */
      last?: string
      /** The newest call's line, shown while the run is live; cleared when a summary settles. */
      line?: string
      /** The last summary made of it. */
      summary?: string
      /** Rows have joined since its last summary settled, or one is on its way. */
      isLive?: true
    }
    /** key `folds`: the closed runs, oldest first. */
    export type Folds = { shape: 1; runs: FoldRun[] }
    /** key `fold`: the open run, or null when there is none. */
    export type OpenFold = FoldRun | null

In `to-human/hooks/mods/folds.tsx`:

    /** Registers the tracker's hooks. `isOn` is the view's "a mark has been seen". */
    export function registerFolds(on: On, view: View, isOn: () => boolean): void

    /** The text a fold's button reads for the run `rowId` stands in, or undefined for `working record`. */
    export function labelOf(folds: Folds | undefined, open: OpenFold | undefined, view: View, rowId: string): string | undefined

    /** One tool call as one line (the live line's table). */
    export function lineOf(tool: string, input: unknown): string

    /** The system prompt of the summary call, as "The model call" gives it. (M2) */
    export const LABEL_SYSTEM: string

`registerToHuman` calls `registerFolds(on, view, () => hasSeenMark)` where it
calls `registerEdits`, and reads the two keys itself where it draws a button
(`$` stays in the file whose hook received it).

Engine calls used: `$.state.get/set`, `$.model.complete`, `$.fs.read/write`,
`$.process.run` (the prune), `$.ui.log`, `$.env.get`, `$.session.id`. No new
dependency.

## Surprises & Discoveries

- Observation: an Anthropic SDK script run from a Claude Code Bash call cannot
  reach the Claude 5 models here: it inherits the session's gateway address,
  and the gateway refuses a request that is not shaped as Claude Code's.
  Evidence: `429 {"type":"rate_limit_error","message":"Error"}` for
  `claude-haiku-5-5`; one `claude --bare -p --model claude-haiku-5-5` launch
  per label answered. The mod itself is unaffected: `$.model.complete` goes
  through the session's client. (Friction tracker:
  `claude-usage-menubar/live/gateway-curl-probe-of-claude-model-gets-429-error.md`.)
- Observation: cache reads cost $0.20 per million tokens on Opus 5.5 and Fable
  5.2, a twentieth and a fortieth of input, not the tenth older models charge.
  Evidence: the claude-api skill's price table (cached 2026-11-03); the first
  estimate of the fork's cost, 4 to 5% of spend from the usual ratios, became
  3.1% at these prices.
- Observation: a delivery folded into a running turn is kept through the door
  `delivery` with its sender's origin; a queue record's origin is the
  engine's; `task` and `from` are props of the drawn row only. The first
  draft, reading the engine's reference, had the kept row carry the engine as
  its origin and looked the sender up on the queue record.
  Evidence: `~/.local/share/fold-runs/evidence/agent-view-before-fix.jsonl`
  (2.1.322): `append delivery {"kind":"peer"}` then
  `append delivery {"kind":"task-notification"}` after a tool result, and
  three `append queue {"kind":"engine"}`.
- Observation: a prompt waiting in the queue is drawn under ids the
  conversation never keeps (a hand-back drew under three before its kept row
  drew under its own), and the prompt being submitted draws as `placeholder`.
  The view keeps each such id in its order for good. As working record they
  cut no run. The follow-up probe then reproduced both harms live: each redraw
  of the person's queued prompt adds an entry of the person's kind, and every
  one cuts the main run (an extra fold with nothing between); a hand-back's
  preview drawn right after a read row becomes the next run's start, and that
  run draws no fold at all. PR #499 is being reworked into one rule for all of
  it: a drawn row the main conversation never kept shapes no run. That work is
  the owner session's, outside this spec.
  Evidence: the same log, `render UserMessage` rids `506ab97e`, `ee71ec46`,
  `79e5fe7e`, then `e42720d2` after `append delivery e42720d2`; and
  `evidence/queued-prompt-full-order.jsonl` lines 5 to 7,
  `queued-handback-full-pane-end.txt`.
- Observation: the person's prompt typed into a running turn is kept through
  the door `delivery` with origin `composer`.
  Evidence: `evidence/queued-prompt-full-renders.jsonl` (2.1.322).
- Observation: the bug that came with this request is reproduced for one
  cause and not confirmed as the owner's. PR #499's probe showed a subagent's
  rows entering the main order once its transcript was opened, and the main
  run's button then drawn on an agent's row, off the main screen; an extra
  fold follows by the same logic where the row that lands is a read row, and
  the PR's unit tests pin that case. Mid-turn deliveries, `SendMessage`, a
  reload, a compaction and a resume of a copy of the owner's transcript each
  folded correctly. The owner's stretch
  held seven groups of mid-turn deliveries and showed at least seven folds,
  which the reproduced cause does not explain by itself: the subagents active
  in that stretch kept four read-class rows in it.
  Evidence: PR #499's body; `~/.local/share/fold-labels/agents_window.py` over
  the session's `subagents/` for 23:01 to 23:22Z.

## Decision Log

- Decision: verification. One independent review of this spec and one of its
  execution section's buildability, both by `doperpowers:adversarial-reviewer`
  (the spec is mechanism-heavy and its design was approved in conversation).
  The branch is reviewed at the end by `doperpowers:reviewer-medium`.
  Rationale: the change is confined to one plugin's drawing and one cheap
  model call, with a failure mode that degrades to today's behaviour; the
  default rung fits. The panel was the alternative and is more than a label
  warrants.
  Date/Author: 2026-11-12, the authoring session (working-record-fold-summaries).
- Decision: three mechanisms settled while writing this spec, after the design
  was approved, none changing what the person sees except as noted. The
  published runs live in `$.state` (the approved design said only that the
  view asks the tracker). A run keeps its last summary until a newer one
  replaces it, where the design said a summary is dropped when the run grows:
  the button shows live lines either way, and a failed second call no longer
  costs the first summary. `TO_HUMAN_FOLD_MODEL` names the model for a launch,
  where the design said there is no setting: the live check needs a way to
  make the call fail without breaking the session's own model.
  Rationale: each is given where it is described above.
  Date/Author: 2026-11-12, the authoring session.

- Decision: the spec review's four findings, all taken (2026-11-13). A kept
  prompt is classified after rebuilding the `from` and `task` its drawing
  carries, with all three outcomes for a prompt folded into a running turn. A
  result kept after its run closed joins that run, and the summary waits for
  the run's results. The open run's turn-end summary is stored, and a resume
  restores stored runs as closed. The tracker's memory is the one authority,
  written out through one chain per destination, and a request is bound to the
  session's epoch as well as its run's generation.
  Rationale: each closed a way for a fold to carry a wrong, partial or lost
  label that the first draft allowed: a channel message or a failed spawn
  splitting or joining runs the view draws otherwise; a `[Bash, message]`
  response summarized without the Bash result; acceptance 4 failing for the
  silent turn rule 2 exists for; two replies overwriting each other, or one
  landing in a cleared session. Restoring the stored open run as open (the
  reviewer's suggestion) was not taken: see "Storage".
  Date/Author: 2026-11-13, the authoring session, from `doperpowers:adversarial-reviewer`.

- Decision: summaries are kept in one file per session, not in `$.store`; and
  the execution review's other findings, taken (2026-11-13): every live check
  that stages the to-human plugin copies the new `types` folder (M1); a reply
  held across a `clear`, `resume` or `fork` is dropped, and tested so; the
  live check quits and resumes right after a silent turn.
  Rationale: the reviewer showed the store probe as written (a version field
  edited under `--plugin-dir`) would not show what an installed update does to
  the store's file. Rather than build the heavier probe, the question is
  removed: a file only its session writes has no cross-session or
  cross-version behaviour to establish, and the appeal mod already keeps its
  log that way. `$.store` with a marketplace-update probe was the alternative.
  Date/Author: 2026-11-13, the authoring session, from `doperpowers:adversarial-reviewer`.

- Decision: a prompt folded into a running turn is classified from its own
  append (door `delivery`, the sender's origin), and the queue-record memory
  is dropped (2026-11-13).
  Rationale: the diagnosis's probe log shows the event carries the sender, and
  shows the queue record does not. The first draft had it the other way
  round, from the engine's reference.
  Date/Author: 2026-11-13, the authoring session.

## Outcomes & Retrospective

Pending — written at finish.
