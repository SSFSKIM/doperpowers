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
- [x] (2026-10-20) Spec reviewed (adversarial design review, buildability review); findings applied in abf65e9e.
- [x] (2026-10-20) M1 — the tool, the view and the notification (to-human plugin): 4101d65d, with the copy and style-gate wave 356ac1cc, reviewed clean
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
reads `message` events, so both work unchanged. sminos reads both message
tools, the plugin's `mcp__to-human__message` and MAWS's
`mcp__maws__message`, as it reads both ask tools today (`ASK_TOOLS` and
`MAWS_ASK_TOOL` in `sminos.py`, `ASK_TOOL` and `mcp__maws__ask` in
`bridge-rows.tsx`). The export belongs to sminos, so a MAWS session's
messages reach the log only if sminos knows MAWS's name:

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
- **Order.** Events reach the log in transcript order, with one exception,
  the one spans already have. A message past `TEXT_CAP` waits for the Stop
  path, so anything the live path writes before that Stop comes ahead of it.
  `log_append_batch` drops a source it already holds rather than moving it.
  A 64k-character message is not a case worth an ordering barrier across
  batches. A call waiting for its result cannot be overtaken: its result is
  written before the next response's rows.
- **The bridge forwards the rows.** `sminos/hooks/mods/bridge-rows.tsx`
  forwards the call's row and its result row to the child, as `keepAsk`
  forwards an ask's. A message past `TEXT_CAP` (65,536 characters) is left
  to the Stop hook's export, as a long span is.
- **The Stop path's flush wait covers a message call.** A turn can end
  right after the tool's result, with no assistant response after it: on an
  Esc, on a hook that stops the continuation, or on an engine-requested turn
  end (bundle 2.1.304 supports all three). Then the Stop payload's
  `last_assistant_message` is empty and `await_flush` returns at once, while
  the transcript writes can still be queued. If the live export is off too,
  the message waits for the next Stop. So when the transcript's tail holds a
  message-tool call, `await_flush` also waits, under the same deadline, until
  that call's result is in the transcript.
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
| MAWS's own tool | `mcp__maws__message`, same input and result (MAWS's). sminos exports it as it exports the plugin's |
| Where the message is | the call's place in the transcript; an accepted call only (its result is not an error) |
| Log event | `kind: "message"`, `src` = the tool-use id |
| Style contract number | 6 (message-tool shape); 7 is MAWS's |

MAWS's side, as its architect stated it:
- (1) Its to-human parser and summaries read a message tool's input as a
  to-human message at the call's place, under both names.
- (2) `mcp__maws__message` beside `mcp__maws__ask` in MAWS launches.
- (3) A supplement naming `mcp__maws__message` (the plugin's tool is not
  available in a MAWS session) beside every message-tool style from 3 up, with
  no shape boundary at 6, and MAWS's full contract moving to 7. So MAWS stops
  losing mid-turn messages when its side lands, whichever release comes first.

The child first verifies the loss on MAWS's own wire with a probe.

The desk's side, as its orchestrator stated it:
- (1) `landed-message.ts` lands a push by tool-use id.
- (2) Optional: the live view draws the text as the input streams. A resync
  can cut the input to its last 65,536 characters, so a partial-JSON reader
  must cope with a missing start.

The desk's session view and channel view are MAWS's renderer (desk-web
imports `owner-marks` and draws MAWS's `Transcript`), so MAWS's side (1)
draws the call there too. The desk builds its side as a MAWS PR after this
spec merges and after MAWS's renderer change, so the two do not conflict.

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
   the Stop hook's (no second copy). sminos's tests show the same for a call
   of `mcp__maws__message`, and for a turn that ends on the tool's result with
   the live export off.
5. A subagent in that session that calls the tool gets the refusal, and
   nothing is drawn, notified or exported.
6. The evals show the effect, counted per message rather than per run.
   - The evals: `tests/output-styles/to-human-agent-step-eval.py` and
     `tests/output-styles/to-human-fanout-eval.py`, at claude-opus-5-5 high,
     both arms with `display: "updates"` and the tool in their tool lists
     (M3's decisions say how).
   - A **mid-turn message** is a span in a text block before a tool call
     (delivered), a call of the message tool (delivered), or a progress note
     the judge rules addressed to the human (lost).
   - A **final message** is a span or a tool call in the response that ends
     the run.
   - Under the new style, lost mid-turn messages are under 25% of mid-turn
     messages, and under half the old style's share.
   - At least 90% of final messages stay spans.
   - Message-tool calls per run are reported, so the token cost is visible.
   - If a threshold is missed, the numbers go back to the spec's author
     rather than the thresholds moving.
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
from to-human (it declares no dependency), so it carries both message-tool
names as its own constant, `MESSAGE_TOOLS`, like `ASK_TOOLS`. Produces the
log event in Interfaces.

**Decisions.**
- Pair the call with its result as `_ask_events` pairs an ask.
- Put the tool's call in the pending set as unanswered asks are.
- A text past `TEXT_CAP` goes to the Stop path, as a long span does. The
  ordering exception that follows is the design's ("Order").
- `await_flush` waits for an unanswered message-tool call at the
  transcript's tail to get its result, under its existing deadline (the
  design says why).
- Every rule above applies to both names in `MESSAGE_TOOLS`.
- `sminos_marks.py` is untouched: the tool branch lives in `host_events`.

**Does not touch.** The to-human plugin, the style, the desk, MAWS.

**Proves.** Acceptance 4 (the export half). The tests must pin:
- the event's shape and `src`;
- record order among spans;
- no event for an errored call;
- the position held for an unanswered call;
- no second copy when both paths run;
- the bridge forwarding the pair;
- each case under `mcp__maws__message` as well;
- a turn that ends on the tool's result, with a delayed transcript flush
  and the live export off: the Stop export waits and writes the message.

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
- Both evals measure acceptance 6's per-message counts:
  - Both arms request `thinking: {type: "adaptive", display: "updates"}`
    (beta `thinking-display-updates-2026-08-18`). A note the new style still
    writes before a tool call must be as visible as the old style's.
  - The artifacts keep each response's blocks in order: text, progress
    notes, tool calls. The agent-step eval's `run()` today flattens
    responses and drops thinking, and its `outcome()` scores a whole run.
    Both change.
  - The tool is in TOOLS from the first request, and its canned result is
    `sent`.
- A progress note is judged with doperpowers-f7's criterion (their audit,
  2026-10-20), at claude-opus-5-5 low effort, on each non-empty progress
  note before a tool call. It counts as a lost message when
  `addressed_to_human` is true. The prompt, word for word:

      A coding agent works for a human who is away from the screen; the human reads only what the agent wraps in <message> tags. The API returned the text below as a short summary of a note the agent wrote between two tool calls; the summary may have dropped any <message> tags.

      <note>
      {note}
      </note>

      Is the original most likely a message to the human (it reports to them, asks them to do or decide something, warns them, answers them, or says what they should expect: addressed to the human, in the second person or as a report written for them), or the agent's own working narration (what it is checking or doing next, for itself)? Answer JSON only: {"addressed_to_human": true|false, "needs_action_from_human": true|false, "why": "<one short clause>"}

- The agent-step eval gains a scenario where the turn keeps working after
  telling the human something: asking them to approve a dialog at a set
  time, then continuing.
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
        description: 'The message, in Markdown.' } },
      required: ['text'] }
    description: 'Send the human a message.'   // when to use it is the style's rule, not the description's
    result (accepted call): 'sent'
    deny (subagent): 'message is for the main conversation; a subagent reaches the human through the session that dispatched it: put this in your report.'

The log event the sminos export writes for an accepted call, in
`host_events`:

    {"kind": "message", "from": <alias>, "to": "host", "text": <input.text>, "src": <tool_use id>}

sminos carries both message-tool names as its own constant, beside
`ASK_TOOLS` in `sminos/skills/sminos/scripts/sminos.py` and beside
`ASK_TOOL` in `sminos/hooks/mods/bridge-rows.tsx`:

    MESSAGE_TOOLS = ("mcp__to-human__message", "mcp__maws__message")

## Surprises & Discoveries

- Observation: the authoring session's own two mid-turn `<message>` spans
  were stored as progress-update thinking blocks with paraphrased text.
  Evidence: transcript df0b714b, lines 154 and 189: `THINK I'll run an eval
  using claude-opus-5-5 (high effort for turns, low effort as judge) across
  30 runs …`.

- Observation: the message tool runs without a permission prompt in both
  `default` and `auto` modes, so no `tool.check` allow was added (M1).
  Evidence: a live check with the worktree's to-human plugin in an isolated
  config (4 haiku calls). The call returned `sent`, the view drew it as
  `● message`, the Notification hook got a `plugin_notification`, and the
  debug log shows `tool.call … resolved by a hooks module` with no permission
  line.
- Observation: subagents still list the tool. The agent definitions that
  withhold compact and the ask tool through `disallowedTools` (this repo's
  `agents/*.md`, the user's `~/.claude/agents/`) do not name it, so a
  subagent sees its definition and gets the refusal if it calls it (M1's
  executor).

- Observation: the Stop path's flush wait reaches a message call only once
  the call's row is on disk when the hook reads the transcript. If the call
  and its result are both still in the engine's write queue (about 100 ms),
  the tail shows no call, and the message goes out at the next Stop, or
  through the bridge when it runs. That is rare, because the hook takes longer
  than one flush to start. An unconditional wait on an empty
  `last_assistant_message` was not added: it would add up to 2 s to every
  Stop after an Esc (M2's executor).

- Observation: the mod reads the active output style cleanly. `$.config.list()`
  has an `outputStyle` row (kind `choice`, provider engine/core) whose
  `value` is `doperpowers:to-human` under the plugin's style and `default`
  with none set. Its `options` list leaves out plugin styles. So the tool is
  registered only under the style (`TO_HUMAN_STYLE` in `message.tsx`), read
  once at `session.start`.
  Evidence: a live probe with no model calls, and on 2.1.306 the debug line
  `mcp__to-human__message visible after 101ms` under the style and no
  register line under `default` (M1's follow-up).
- Observation: MAWS's side landed on MAWS master as 82a0967ff (P4-R7, entry
  48 in its P4 Decision Log).
  - `mcp__maws__message` answers an accepted call with `sent`, and is always
    loaded and allowed at launch.
  - Every MAWS reader takes either tool name.
  - MAWS's full contract is 7, and its supplement sits beside every
    message-tool style except 7.
  - The desk's `landed-message.ts` case is with smns-erb-71 (b4948247).
  Evidence: MAWS's eval on its own wire (claude-opus-5-5, high effort) lost 4
  of 11 mid-turn messages before, all four asking the owner to act, and 0 of
  11 after. Relayed by doperpowers-88.

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

- Decision: The spec review's findings applied.
  - sminos exports both message-tool names (`MESSAGE_TOOLS`), since a MAWS
    session's messages reach the log only through sminos.
  - The Stop path's flush wait covers a turn ending on the tool's result.
    The claim that a tool result is always followed by an assistant response
    was false: Esc, continuation-stopping hooks, engine-requested turn ends.
  - The ordering guarantee is narrowed to the exception spans already have
    (a message past `TEXT_CAP`), instead of a cross-batch ordering barrier.
  - The evals count per message, with doperpowers-f7's judge criterion and
    `display: "updates"` in both arms (buildability review, and f7).
  - The desk's drawing is folded into MAWS's renderer change (the desk
    orchestrator).
  Rationale: The rejected alternative was a barrier holding every later
  event behind a deferred long message. It is machinery for a 64k-character
  message, which no session sends.
  Date/Author: 2026-10-20, doperpowers-88.
- Decision: MAWS drops its shape boundary at 6. Its `mcp__maws__message`
  supplement goes beside every message-tool style from 3 up. Nothing in the
  contract table moves: 6 stays the plugin's number, and 7 stays MAWS's.
  Rationale: With a boundary, a MAWS session kept losing mid-turn messages
  until this plugin's style declared 6. Without one, MAWS's fix depends on
  MAWS's release alone.
  Date/Author: 2026-10-20, the MAWS architect, recorded by doperpowers-88.

- Decision: M1's gaps, resolved by its executor.
  - A call whose `text` is missing or blank is refused (`EMPTY_REFUSAL` in
    `message.tsx`, outside the contract), so an empty message is never drawn,
    notified or exported.
  - An interrupted call counts as unsent, as an errored one does. One set of
    unsent ids keeps the call row and its result row in agreement.
  - In the band's full-transcript mode the call and its result draw the
    engine's own rows. The empty result row applies only while the view folds.
  - Streaming input that arrives as a string is partial JSON, and the text so
    far is drawn. An object is whole. Nothing draws before any text arrives.
  - `previewLine` lives in `notify.tsx` and `message.tsx` imports it. The
    import cycle (message → notify → to-human → message) is safe: every
    cross-module use is inside a function.
  Date/Author: 2026-10-20, M1's executor, folded by the plan-executor.
- Decision: M3 adds `mcp__to-human__message` to the `disallowedTools` of
  this repo's `agents/*.md`, beside compact and the ask tool. Subagents then
  stop paying for a definition they can only be refused. The user's own
  `~/.claude/agents/` is outside the repository and goes back to the spec's
  author.
  Rationale: The repo already withholds the main-conversation-only tools this
  way (CLAUDE.md, the `hooks/` row). The refusal stays the guarantee for
  built-in types and forks.
  Date/Author: 2026-10-20, the plan-executor.
- Decision: rebase onto `origin/main` after M1 and M2 are reviewed clean and
  before M3 dispatches. M3 edits the style and the agent-step eval, which
  7.198.0 changed on main. The versions are bumped again past main at the end.
  Date/Author: 2026-10-20, the plan-executor.

- Decision: M2's gaps, resolved by its executor.
  - A message-tool call's event sits at the call's position among its
    record's blocks. A span's `src` index is unchanged.
  - An accepted call whose text is missing or blank yields no event (M1
    refuses one anyway). The text is exported word for word, not trimmed.
  - The bridge forwards a refused or errored pair to the child, and
    `host_events` drops it, as it does a refused async ask.
  - `TEXT_CAP` is checked once the call and its result are both kept, in
    either row order.
  - `keepAsk`, `state.asks` and `ASKS_KEPT` are renamed `keepPair`,
    `state.pairs` and `PAIRS_KEPT` inside the sminos bridge modules, since
    the map now holds message calls too.
  - The flush wait reads the transcript's last message past its tool
    results, under the existing deadline.
  Date/Author: 2026-10-20, M2's executor, folded by the plan-executor.
- Decision: subagents do not get the message tool for now. M3 adds
  `mcp__to-human__message` to the `disallowedTools` of every `agents/*.md`
  that already withholds `mcp__sminos__AskUserQuestion` (nine files). The
  `agentId` refusal stays, and a pointer to SSFSKIM/doperpowers#310 sits
  beside it in `message.tsx`. #310 is the ticket for letting a subagent
  message the human directly, not built here.
  Rationale: The human's ruling, relayed by the spec's author. It replaces
  the earlier entry that left this to M3's judgment.
  Date/Author: 2026-10-20, the human, recorded by the plan-executor.

- Decision: M2's live export holds its order behind a message call (the
  review's finding). Everything kept after an ordinary call on the main loop
  queues until the call's pair is whole, refused or errored pairs included,
  and is released in transcript order. A row holding a call is exported
  whole with the pair. A call whose result never reaches the bridge holds at
  most `PAIRS_KEPT` (50) exports, after which the queue flows and the Stop
  hook exports the call. An over-cap call holds nothing. An async ask's pair
  still does not hold what follows it, as before M2.
  Date/Author: 2026-10-20, M2's executor, folded by the plan-executor.
- Decision: tool-only messaging was considered and rejected for now. That
  means every message through the tool, with `<message>` kept only as a
  fallback.
  Rationale: An agent cannot end a turn on a tool use, since the harness asks
  for a visible reply after the result. A final message sent through the tool
  would cost one more request over the whole context at every turn end. A
  `preventContinuation` hook might end the turn after the call, but that is
  untested. Every reader already reads both forms, so revisiting this later
  changes only the style.
  Date/Author: 2026-10-20, the human, recorded by doperpowers-88.
- Decision: the rule for when to use the tool lives in the style, its one
  source. The tool's description only names it: `Send the human a message.`
  The field reads `The message, in Markdown.` The name, input, result and
  refusals are unchanged, so the contract table stands. The tool is
  registered only under the to-human output style, if the mod can read the
  active style cleanly at `session.start`. Otherwise registration stays as
  it is and the gap goes in TECH-DEBT.md.
  Rationale: A session with the plugin but under another style would
  otherwise see a tool whose description gives no rule.
  Date/Author: 2026-10-20, the human, recorded by the plan-executor.

- Decision: the live export's hold works on whole rows (M2's second review).
  A row holding message calls waits until every call in it has its result,
  then goes out once with all of them, so `[A, B, span C]` reaches the log
  as A, B, C in either result order. A row given up at the `PAIRS_KEPT`
  bound goes out with the results it has. Dedup cannot move an event already
  appended, so per-call exports of a shared row were unsafe.
  Date/Author: 2026-10-20, M2's executor, folded by the plan-executor.

## Outcomes & Retrospective

Pending — written at finish.
