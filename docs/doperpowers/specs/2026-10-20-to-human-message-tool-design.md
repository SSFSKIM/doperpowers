# The to-human message tool

A session under the to-human output style reaches its human only through
what it marks: today, `<message>…</message>` spans in its assistant text. On
`claude-opus-5-5` and `claude-fable-5-1` (and `claude-sonnet-5-5`), a span
written before a tool call in the same response does not come back from the
API as text. Notes longer than a sentence or two between tool calls are
returned as progress-update `thinking` blocks, which are paraphrases without
their `<message>` tags, and they are empty unless the request sets
`thinking.display: "updates"`. So a message sent mid-turn reaches none of its
consumers: the report view, the notification, the sminos export to the
project log, the desk, and MAWS. After this change, a session sends that
message as the input of a plugin tool, `mcp__to-human__message`. Tool input is
never summarized, so the message arrives word for word. The report view draws
it where the call sits, the notification fires, and the export writes it to
the project log, where the desk pushes it to the phone. Messages at the end of
a turn keep arriving as `<message>` spans, as they do now.

To see it working: launch a session with the worktree's plugins, ask it to
tell you something and then keep working. The report shows the message at its
place between the tool calls, a notification is raised, and
`sminos chat` lists the message in the project's log (acceptance 1–5).

The human approved the direction on 2026-10-20 ("yes let's make a message
tool") and its home ("building it under to-human plugin could be better",
always loaded, not deferred), after weighing the cost below.

## Progress

- [x] (2026-10-20) Design closed in the authoring session (doperpowers-88);
  consumers mapped across doperpowers, MAWS and the desk; MAWS architect and
  desk orchestrator briefed.
- [ ] M1 — the tool, the view and the notification (to-human plugin)
- [ ] M2 — the export (sminos)
- [ ] M3 — the style, the evals, the docs, acceptance

## The loss, measured

- On this machine, interactive main sessions over the 3 days before
  2026-10-20: `claude-opus-5-5` returned 330 non-empty `thinking` blocks
  right before a `tool_use`, and `claude-fable-5-1` 315. Many of them were
  messages to the human. One asked them to click "Don't Allow" on a dialog on
  the mini. In the same window, 145 `<message>` text blocks survived
  alongside a tool call (short ones).
- doperpowers-f7's audit since 7.185.0: about 33 of 85 judged progress blocks
  read as messages to the human, 13 of them asking for an action (for
  example, approve a codesign key prompt at 07:15). 32 spans before a tool
  call survived as text. About half the mid-turn messages were lost.
  Progress blocks first appear in this machine's transcripts on 2026-10-02.
- The fan-out eval of 2026-10-20 (`tests/output-styles/to-human-fanout-eval.py`):
  all 12 announcements the model made before a launch came back as progress
  notes, none as text.
- The API documents this as a response-shape change of the 5.5 models and
  Fable 5.1 (the claude-api skill's `shared/model-migration.md`, "Text
  between tool calls comes back in thinking blocks"). Its fix for verbatim
  mid-turn content is a send-message tool declared at session start, because
  tool inputs are never summarized.
- Friction tracker: SSFSKIM/doperpowers#304.

## Why a tool, and the alternatives that lost

| Option | Why it lost |
|---|---|
| A tool for mid-turn messages (chosen) | — |
| A style rule keeping mid-turn messages to a sentence or two | The cutoff is the API's, undocumented as exact, and cuts real content. |
| The model ends its response after a mid-turn message; a mod starts the next turn | One full-context round trip per message (about $0.06 at 300k tokens on Opus 5.5) and the wait; every turn-end hook (Stop, the sminos export, the compaction offer) runs each time; and the model has to end its response on purpose mid-work, which it does unreliably. |
| Strip the tool call from context after sending, leaving a short note | The call sits in the same assistant turn as that turn's signed thinking blocks. Editing that turn drops its thinking on Opus 5.5 and Fable 5.1, and returns a 400 on accounts the history-editing check enforces. It saves ~99 tokens plus the text, and the model loses the exact words it sent. |
| Recover the text from the progress block | The API returns only a paraphrase. The full note is encrypted in the block's signature. |
| Every message through the tool | ~99 tokens each for the messages at the end of a turn (about 80–85% of messages on this machine), which already arrive as text. |

Cost of the chosen design, measured with `count_tokens` on
`claude-opus-5-5`: the tool's definition is 129 tokens, the style paragraph
about 75 (both once per session, both cached), and each message sent through
the tool about 99 tokens over the same text as a span. The message text
itself costs the same either way. A median session on this machine sends 1
message mid-turn (about 300 tokens added in all), the 90th percentile 10
(about 1.2k), the heaviest at most 230 (9k–23k). The tool is called in the
same response as the next work call, so it adds no round trip.

## The design

### The tool

It is registered by the to-human plugin. The plugin owns what the human
reads: the view that draws the call and the notification ship with the tool,
so a session that has the tool has a view that knows it. sminos reads
transcripts, so it needs only the name. The ask tool lives in sminos for a
reason that does not apply here: answers route back in through the bridge
and the desk, while a message goes one way and only has to land in the
transcript.

- **Name**: `message`, which the engine exposes as `mcp__to-human__message`.
  A plugin tool is `mcp__<plugin>__<name>`, and the engine replaces only
  `[^a-zA-Z0-9_-]`, so the hyphen survives (bundle 2.1.304:
  `` F5 = (e,n) => `mcp__${Bn(e)}__${n}` ``). A test pins the full name
  that `register()` returns.
- **Input**: one string field, `text`, the message in Markdown: what the
  model would have written inside the span. A single string keeps the desk's
  plane and web treating the input as opaque JSON (constraint (c) of the
  desk orchestrator).
- **Result**: `sent`.
- **Registered** at `session.start` of an interactive session, as the ask
  tool is, and not when `MAWS_NATIVE_TO_HUMAN` is set. MAWS launches register
  their own `mcp__maws__message` (MAWS's side, below), as they register
  `mcp__maws__ask` in place of the sminos ask. A non-interactive session (`claude -p`)
  has no tool; nobody reads its report.
- **Always loaded**: the `tool.describe` hook returns `isDeferred: false`
  for it (the ask's and compact's pattern). A deferred tool would cost a
  ToolSearch before the first message, and its definition would land in
  context anyway.
- **A subagent's call is refused**: `{ deny: … }` when `e.agentId` is set,
  as compact does. Only the main conversation reaches the human. A
  subagent's words reach them through the session that dispatched it.
- **Never waits on a permission prompt.** The ask and compact tools run
  without prompts today. If M1's live check shows a prompt under any
  permission mode, the plugin adds a `tool.check` allow for its own tool
  (`hooks/mods/appeal.tsx` has the pattern).
- **Copy** (the description the model reads, and the refusal) is fixed in
  Interfaces.

### When the model uses it

The output style, `output-styles/to-human.md` in doperpowers:

- A message sent before another tool call goes through the tool, called in
  the same response as that call. The style says why in a clause: written as
  text there, it comes back as a paraphrase that never reaches the human.
  The reason lets the model generalize, for example to a message it sends
  and then keeps working.
- A message at the end of a turn stays a `<message>` span.
- Where the tool is not among the session's tools, a span is the only form.
- The sentence "Only what you wrap in `<message>…</message>` is delivered to
  the human; each span, wherever you write it, is one message" becomes true
  again by naming both forms.
- Everything that shapes a message's content (the ⚠ Critical block, the
  Insight block, the fan-out notice) applies to the tool's text as to a
  span's.
- The front matter declares `maws-to-human-contract: 6`. MAWS reads a
  declaration by its shape (`src/shared/owner/contract.ts`, `styleShape`): any
  number from 3 up, other than 5, is the message-tool shape. So today's MAWS
  reads 6 as it reads 4. 5 is MAWS's own full contract, and 7 is reserved for
  MAWS's next one (the MAWS architect, 2026-10-20). The style's `description`
  names both forms.

The exact wording is M3's, written under doperpowers:writing-skills and
proved by the evals (acceptance 6). This section fixes what the wording must
achieve.

### The view (`to-human/hooks/mods/to-human.tsx`)

- The tool's `ToolUse` row draws as a message, as a span does: the label,
  then the text as a `Markdown` element. It counts as a row the human reads
  (`isRead`), so it breaks a run of working record, and it turns the view on
  (`hasSeenMark`) as a span does.
- Its `ToolResult` row draws nothing (`<Box />`), as the ask's result does
  in `sminos/hooks/mods/ask.tsx`.
- A refused or errored call draws the engine's own row inside the working
  record. It was not sent.
- `sentMark`, which decides at module start whether the conversation holds a
  mark, counts the tool's calls in `$.session.messages()` (`toolUses`) as
  marks too.
- While the call's input is still streaming (`isRunning`), the row draws
  the text parsed so far, or nothing until the input is whole. Never raw
  JSON.
- Under MAWS (`native()`) nothing changes: the view already defers every
  surface but the terminal to MAWS.

### The notification (`to-human/hooks/mods/notify.tsx`)

- The tool's message raises `$.ui.notify` from the tool's call handler, once
  the call is accepted: the same one-line preview rule as a span's (first
  line, at most 200 characters).
- It is main conversation only, and never under `SMNS_INTERNAL`, as today.
- Raising it from the handler, not from the row's `session.append`, is what
  keeps a refused call from notifying (the explorer's finding: the row is
  kept before the call runs).
- `notify.tsx`'s existing rule that a `tool_use` block in a response row
  raises nothing stays. The handler is the one path.

### The export (sminos)

The project log gets the tool's message as the same event a span gives.
desk-hub pushes on a fresh `message` event, and the desk's channel stream
reads `message` events, so both work unchanged:

    {"kind": "message", "from": <alias>, "to": "host", "text": <input.text>, "src": <tool_use id>}

- **`src` is the tool-use id**, the shape an async question already uses. A
  span's `src` is `<record uuid>#<span index>`, and a span index means
  nothing for a tool call. The desk's landing gains a third case keyed by
  tool-use id, after its `callRow` precedent (the desk's side).
- **Only an accepted call counts.** A call is exported once its result is in
  the transcript and is not an error, paired as `_ask_events` pairs an ask
  with its result. The export position does not pass an unanswered call
  (`export_host`'s pending set).
- **One reader, both paths.** `host_events` in
  `sminos/skills/sminos/scripts/sminos.py` emits the event, in record order
  with the spans. `export_live` (the bridge's path) and `export_host` (the
  Stop hook's) both call it.
- **The bridge forwards the rows.** `sminos/hooks/mods/bridge-rows.tsx`
  forwards the call's row and its result row to the child, as `keepAsk`
  forwards an ask's. A message past `TEXT_CAP` (65,536 characters) is left
  to the Stop hook's export, as a long span is.
- `await_flush` is unchanged. A tool result is always followed by an
  assistant response, so a turn never ends on the tool's row.
- Dedup stays `(kind, src)`.
- Rows an Esc or a `/rewind` cut off the chain behave as spans do today:
  exported as written.

### The cross-repo contract (MAWS and the desk build their sides)

This spec's milestones change doperpowers only. MAWS's architect
(`37052769`) routes MAWS's side as a P4 child, and the desk orchestrator
(`b4948247`) routes the desk's. Both build against this contract:

| Item | Value |
|---|---|
| The plugin tool | `mcp__to-human__message`, input `{"text": string}` (Markdown), result `sent` |
| MAWS's own tool | `mcp__maws__message`, same input and result (MAWS's) |
| Where the message is | the call's place in the transcript; an accepted call only (its result is not an error) |
| Log event | `kind: "message"`, `src` = the tool-use id |
| Style contract number | 6 (message-tool shape); 7 is MAWS's |

MAWS's side, as its architect stated it:
- (1) Its to-human parser and summaries read a message tool's input as a
  to-human message at the call's place, under both names.
- (2) `mcp__maws__message` beside `mcp__maws__ask` in MAWS launches.
- (3) A shape boundary at 6 with a supplement naming `mcp__maws__message`,
  and MAWS's full contract moving to 7.

The child first verifies the loss on MAWS's own wire with a probe.

The desk's side, as its orchestrator stated it:
- (1) `landed-message.ts` lands a push by tool-use id.
- (2) The session view and channel view (MAWS's renderer) draw the call as a
  message.
- (3) Optional: the live view draws the text as the input streams. A resync
  can cut the input to its last 65,536 characters, so a partial-JSON reader
  must cope with a missing start.

**What the human sees while the sides land.** Today, every mid-turn message
is lost everywhere. Once this spec ships, the terminal report and the
notification show tool messages, and the project log carries them, so the
desk's push and channel stream do too. The desk's session view and MAWS fold
the call among MCP calls until their sides land. A push for a tool message
lands as missing until the desk's landing has its third case. That is the
one regression: a short mid-turn message that survives as text today, and
that the model sends through the tool instead, is not drawn in the desk's
session view until then. It is accepted: the same message reaches the
terminal, the notification, the push and the channel stream, and every
message that is lost today starts arriving.

### Not in scope

- `transcript_reply`, a seat's reply to its orchestrator, which takes the
  last assistant text.
- `sminos watch`, which prints the call as one line: enough.
- `hooks/to-human-stream.sh`, which streams text labels only.
- The sminos ask tool.
- Any change to how a span is parsed.

## Acceptance

Each is checked in M3 against the worktree's plugins.

1. In a live interactive session with the worktree's to-human and sminos
   plugins (`--plugin-dir`), prompted to tell the human something and then
   run a command, the transcript holds a `tool_use` of
   `mcp__to-human__message` in the same response as the command's call. Its
   result is `sent`, and no permission prompt appears.
2. In that session, the report view (to-human's view, the band showing the
   report) draws the message as a message row between the tool calls, not
   folded into the working record, and draws no row for its result.
3. A notification is raised for it: a `Notification` hook in the check's
   isolated config receives a `plugin_notification` carrying the message's
   first line.
4. `sminos chat` (the project's log) lists the message once, with the text
   word for word, and its log event has `kind: "message"` and `src` equal to
   the tool-use id. That holds after the bridge's live export and again after
   the Stop hook's (no second copy).
5. A subagent in that session that calls the tool gets the refusal, and
   nothing is drawn, notified or exported.
6. The evals show the effect:
   - `tests/output-styles/to-human-agent-step-eval.py`, extended per
     doperpowers-f7's three conditions (below), and
     `tests/output-styles/to-human-fanout-eval.py`, with the tool in their
     tool lists, at claude-opus-5-5 high.
   - The new style sends through the tool most messages that, under the old
     style, went into progress notes.
   - The share of messages that reach the human (a span in a text block, or
     a call of the tool) rises against the old style.
   - End-of-turn messages stay spans.
   - Tool calls per run are recorded, so the token cost is visible.
   - The numbers go in each eval's docstring and in the PR.
7. The suites pass: `to-human/tests/mods/run.sh`,
   `sminos/tests/run-sminos-tests.sh`, `sminos/tests/mods/run.sh`,
   `tests/mods/typecheck.sh`, and `ci-gate` GREEN on the branch head.

## Execution

### Constraints that bind every milestone

- Version bumps go in the same commit as the change, through
  `scripts/bump-version.sh` (`--plugin to-human` in M1, `--plugin sminos` in
  M2, doperpowers in M3), each to the next minor above what `origin/main`
  holds when the PR is opened.
- The tool's name, input, result and log-event shape are the Interfaces
  below. Nothing renames them.
- Function hooks: `$` may only be passed to functions in the same file. The
  engine admits one unmatched registration of an event per module, so new
  hooks take matchers (`hooks/mods/README.md`).
- The style is behavior-shaping content: its wording changes under
  doperpowers:writing-skills, with the eval evidence in the PR
  (CLAUDE.md, "Skill Changes Require Evaluation").
- One PR for the three milestones, so the tool, its readers and the style
  that tells the model to use it ship together.

### Plan of Work

### M1 — the tool, the view and the notification

**What exists at its end.** A session with the worktree's to-human plugin
has `mcp__to-human__message` loaded from its first request:
- A call returns `sent`.
- The report view draws the call as a message row and its result as
  nothing.
- A notification is raised once the call is accepted.
- A subagent's call is refused.

**What it touches.**
- A new `to-human/hooks/mods/message.tsx`, registered from
  `to-human/hooks/mods/register.tsx`.
- `to-human/hooks/mods/to-human.tsx`: the `ToolUse` and `ToolResult` hooks
  for the tool, `isRead`, and `sentMark`.
- `to-human/hooks/mods/notify.tsx`: the preview rule, shared without `$`.
- `to-human/hooks/hooks.json`: its description.
- Tests in `to-human/tests/mods/`.
- The to-human plugin's version.

**Interfaces.** Exposes `MESSAGE_TOOL` (the full name) and the tool's
contract, both in Interfaces below.

**Decisions.**
- Registration mirrors `askStart` in `sminos/hooks/mods/ask.tsx`
  (`session.start` with `isInteractive: true`, skipped under
  `MAWS_NATIVE_TO_HUMAN`).
- `tool.describe` for the tool returns `isDeferred: false`.
- The `tool.call` handler denies a subagent's call (`e.agentId`), raises
  the notification, and answers `sent`.
- Rendering reuses the view's own message element, so a tool message and a
  span look the same.
- A plugin's render hooks run on its own tool's rows: the ask draws its own
  `ToolUse` and `ToolResult`.
- Verify live whether the call prompts for permission in `default` and
  `auto` modes. If it does, add a `tool.check` allow for the tool alone
  (appeal's pattern), and record which in Surprises & Discoveries.

**Does not touch.** sminos, the output style, MAWS.

**Proves.** Acceptance 1, 2, 3 and 5. The tests must pin:
- the full tool name;
- `isDeferred: false`;
- the refusal for a subagent;
- the call row drawn as a message, with partial input drawn without raw
  JSON;
- the result row drawn empty;
- an errored call left as working record;
- `sentMark` true for a conversation holding only a tool message;
- no notification for a refused call.

### M2 — the export

**What exists at its end.** A transcript holding an accepted call of the
tool yields one `message` event with `src` = the tool-use id at the call's
place, through both export paths. A call without a result yet holds the
export position, and an errored one yields nothing.

**What it touches.**
- `sminos/skills/sminos/scripts/sminos.py`: `host_events`, the pairing
  beside `_ask_events`, and `export_host`'s pending set.
- `sminos/hooks/mods/bridge-rows.tsx`: forwarding the call and result rows,
  and the cap.
- Tests: `sminos/tests/run-sminos-tests.sh` cases,
  `sminos/tests/test-bridge-export.sh`, `sminos/tests/mods/bridge.test.ts`.
- The sminos plugin's version.

**Interfaces.** Consumes `MESSAGE_TOOL` by value. sminos imports nothing
from to-human (it declares no dependency), so it carries the name as its own
constant, like `ASK_TOOLS`. Produces the log event in Interfaces.

**Decisions.**
- Pair the call with its result as `_ask_events` pairs an ask.
- Put the tool's call in the pending set as unanswered asks are.
- A text past `TEXT_CAP` goes to the Stop path, as a long span does.
- `await_flush` stays as it is (the design says why).
- `sminos_marks.py` is untouched: the tool branch lives in `host_events`.

**Does not touch.** The to-human plugin, the style, the desk, MAWS.

**Proves.** Acceptance 4 (the export half). The tests must pin:
- the event's shape and `src`;
- record order among spans;
- no event for an errored call;
- the position held for an unanswered call;
- no second copy when both paths run;
- the bridge forwarding the pair.

### M3 — the style, the evals, the docs, acceptance

**What exists at its end.**
- The output style tells the model when to use the tool and declares
  contract 6.
- The two evals measure the before and after with the tool in their tool
  lists.
- The docs that teach how a session messages its human name the tool.
- Acceptance 1–7 is run and recorded.

**What it touches.**
- `output-styles/to-human.md` and the doperpowers version.
- `tests/output-styles/to-human-agent-step-eval.py` and
  `tests/output-styles/to-human-fanout-eval.py`.
- Docs: `sminos/skills/sminos/SKILL.md` and
  `sminos/skills/sminos/references/spawn-preamble.md`, where they teach the
  `<message>` mark; `CLAUDE.md`'s `to-human/`, `output-styles/` and
  `sminos/` rows; and `README.md` if it describes the mark.
- A live check beside `to-human/tests/mods/live-resume-check.py`, in the
  same isolated pattern.

**Interfaces.** Consumes `MESSAGE_TOOL` and the log event.

**Decisions.**
- The style wording is drafted under doperpowers:writing-skills against the
  design's "When the model uses it", then tested.
- The agent-step eval takes doperpowers-f7's three conditions:
  - its "before" arm requests `thinking.display: "updates"` (beta
    `thinking-display-updates-2026-08-18`) and counts messages that went
    into progress notes;
  - "reached" counts a call of the tool alongside `<message>` and the ask;
  - the tool is in TOOLS from the first request.
- The agent-step eval gains a scenario where the turn keeps working after
  telling the human something: asking them to approve a dialog at a set
  time, then continuing.
- The fan-out eval adds the tool to TOOLS and counts its calls as reaching
  the human.
- doperpowers-f7 (`e7f55ccc`) wrote the agent-step eval. Tell them when the
  change is pushed, so they can read it.
- The live check spends model calls, so no suite runs it. It is run by hand,
  as the resume check is.

**Does not touch.** The plugins' code, except what an acceptance failure
sends back to M1 or M2.

**Proves.** Acceptance 1–7, end to end. Concrete Steps has the commands.

### Concrete Steps

Working directory: the branch's worktree.

    to-human/tests/mods/run.sh                 # M1: all pass
    sminos/tests/run-sminos-tests.sh           # M2: all pass
    sminos/tests/mods/run.sh                   # M2: all pass
    tests/mods/typecheck.sh                    # every milestone: no errors
    to-human/tests/mods/live-message-check.py  # M3: acceptance 1–5, prints PASS per item (spends model calls)
    ANTHROPIC_API_KEY="$(cat ~/.config/claude-secrets/ANTHROPIC_API_KEY)" \
      python3 tests/output-styles/to-human-agent-step-eval.py control=<old style> variant=output-styles/to-human.md --reps 4
    ANTHROPIC_API_KEY="$(cat ~/.config/claude-secrets/ANTHROPIC_API_KEY)" \
      python3 tests/output-styles/to-human-fanout-eval.py control=<old style> variant=output-styles/to-human.md --reps 4
    /Users/new/.claude/plugins/cache/doperpowers/ci-kit/*/bin/ci-gate   # GREEN

`<old style>` is `<(git show origin/main:output-styles/to-human.md)`. A
model call spent on a fan-out is announced to the human first, per the
style.

### Interfaces and Dependencies

In `to-human/hooks/mods/message.tsx`:

    export const MESSAGE_TOOL = 'mcp__to-human__message'   // the name register() returns; a test pins it

The tool as registered:

    name: 'message'
    inputSchema: { type: 'object', properties: { text: { type: 'string',
        description: 'The message, in Markdown: what you would write inside <message>…</message>.' } },
      required: ['text'] }
    description: 'Send the human a message now, word for word. Use it for a message you send before another tool call, in the same response as that call; a message at the end of your turn stays a <message> span.'
    result (accepted call): 'sent'
    deny (subagent): 'message is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.'

The log event the sminos export writes for an accepted call, in
`host_events`:

    {"kind": "message", "from": <alias>, "to": "host", "text": <input.text>, "src": <tool_use id>}

sminos carries the tool's name as its own constant beside `ASK_TOOLS` in
`sminos/skills/sminos/scripts/sminos.py`, and in
`sminos/hooks/mods/bridge-rows.tsx` beside `ASK_TOOL`.

## Surprises & Discoveries

- Observation: the authoring session's own two mid-turn `<message>` spans
  were stored as progress-update thinking blocks with paraphrased text.
  Evidence: transcript df0b714b, lines 154 and 189: `THINK I'll run an eval
  using claude-opus-5-5 (high effort for turns, low effort as judge) across
  30 runs …`.

## Decision Log

- Decision: Verification. One independent spec review by
  `doperpowers:adversarial-reviewer` (a technical-heavy spec), plus its
  buildability review of the execution section (three milestones), in the
  same round. The branch review at the end is doperpowers:review-code at
  rung high (`doperpowers:reviewer-high`), because the change spans two
  plugins and the style, and fixes a contract that MAWS and the desk build
  on.
  Rationale: execspec's default plus the multi-milestone review. Rung high
  for a human-facing delivery path shared across repositories.
  Date/Author: 2026-10-20, doperpowers-88.

## Outcomes & Retrospective

Pending — written at finish.
