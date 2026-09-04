# The Human Stream — Design

A Claude Code session's transcript is two things at once: the agent's working
record (every tool call, every intermediate thought) and the only surface the
human has for reading what the agent is doing. This design separates them. An
agent decides for itself which words the human should read and marks those,
and only those, by wrapping them in a tag inside its ordinary messages; the
human reads the marked words — for one session, or for every session at once
— and opens the transcript only when they want to look inside. The transcript
stays the single record; the stream is a view of it.

This is plumbing for a consumer that does not exist yet: `afleet`
(`~/Developer/GitHub/afleet`), a GUI workspace for coding agents whose default
view is the agents' reports to the human, with the full transcript folded
behind a click. The tag and the reading rule in §2 are the contract between
the agent, afleet, and any other reader (`sminos inbox` among them). Nothing
here is built now; this document records the decisions so that the build,
when it comes, does not re-derive them.

Human-confirmed frame (2026-09-05): direction is agent → human only (the
human's replies ride the existing `SendMessage` and `sminos send`); the mark is
a tag in the message, not a command; the per-session and all-sessions views
are the same scan with a filter; no message kinds; every session is a source,
seats and seatless interactive sessions alike; the agent-facing instruction is
one sentence, with no list of what to send or withhold; deferred until afleet
plumbs it.

## §1 The agent's side

No verb. The agent writes, and wraps what the human should read:

    <to-human>
    The migration is applied; two tables changed shape. Nothing needs you
    until the review lands.
    </to-human>

The doctrine is one sentence: *your tool results and messages are not shown to
the human; wrap what the human should read in `<to-human>…</to-human>`.* It is
carried by an output style — `output-styles/to-human.md` in this plugin, which
the harness injects as persistent context at session start and after every
compaction, and which also carries the explanatory-insights style so a session
loses nothing by selecting it. A launcher whose surface is the stream (afleet)
selects it with `"outputStyle": "to-human"` in the settings file it passes at
launch; a seat spawned for such a surface gets the same setting; every other
session on the machine is untouched, and a human in a plain session can turn
it on or off with the output-style command. No kinds, no
criteria, no cadence. The judgment of what a human needs to hear is the
agent's, and it is expected to be good; if observed failures show otherwise,
the doctrine is refined from those failures, not from anticipation.

Consequences worth stating. A tag costs the agent nothing — no tool call, no
turn, no permission prompt — and it can appear anywhere the agent writes
text, including between tool calls mid-turn. An agent's closing message of a
turn is not shown in afleet's default view either, so an agent that wants the
human to see its summary wraps it. The one sentence covers both without
saying them.

## §2 The contract — where the words are and how a reader finds them

The words live where the harness already puts them: the session's transcript,

    ~/.claude/projects/<cwd-slug>/<session-id>.jsonl

one JSON record per line. The reading rule, for afleet and every other
consumer:

1. Take records with `type == "assistant"` and `isSidechain` false — the main
   line of the session, not a subagent's — and skip the `agent-*.jsonl` files
   beside a session's transcript, which are subagent transcripts. Subagents do
   not address the human.
2. Within `message.content`, take blocks with `type == "text"`. Tool-use
   blocks, tool results, user records, and peer messages are never scanned,
   so a tag quoted inside any of those can never surface.
3. In each text block, every `<to-human>…</to-human>` span is one message to
   the human, in order. The tag opens and closes within one assistant
   message; a reader joins the text blocks of one message (same `uuid`)
   before matching, so a span split by streaming is still one span.
4. Each message carries the record's `sessionId` and `timestamp`. The session
   name comes from the transcript's own `custom-title` / `agent-name`
   records, or from the harness peer registry while the session is live; the
   seat comes from the sminos registry (the seat whose `current` is this
   session), when there is one. Both are read-time joins — the transcript is
   the truth and carries neither.

Because the words never leave the transcript, the human view and the log
cannot disagree, a consumer can show a span while it is still streaming, and
there is nothing for sminos to write, lock, or rotate.

Scale on this machine, for the reader's design: 1.5 GB of transcripts in
1,206 files across 111 project directories, 642 of them subagent files the
rule skips, about eighty files touched in a day and 680 in a week. A consumer
keeps a per-file byte offset and reads only growth; a one-shot reader bounds
itself by file modification time.

## §3 The human's side

afleet renders the stream per session and across all sessions by applying §2
to one file or to every file under `~/.claude/projects/`. Nothing else is
needed from sminos.

For a terminal, and as the reference reader, sminos grows one verb:

    sminos inbox                          # every session touched in the last day, oldest first
    sminos inbox --session <id|prefix|name>
    sminos inbox --group <group>          # sessions filling a seat in the group
    sminos inbox --since 7d               # widen the window
    sminos inbox -n 20                    # the last N
    sminos inbox --json                   # {session, name, seat, ts, text} per line

sminos already reads transcripts (`reply`, the delivery evidence in
`wake --wait`), so `inbox` is the same scan with §2's rule and a modification
time window. `--session` resolves a full id, an id prefix, or a session name.

`sminos tui` may later show the focused seat's recent stream in its panel;
that is a possible slice, not a commitment of this design — afleet is the
intended reading surface.

## §4 What this is not

- Not a replacement for `status` (the one-line "what I am doing now"),
  `reply` (a turn's final answer), or the pending-question rendering of a
  blocked seat. Those describe state; the stream is the agent addressing the
  human. A later cut may fold pending questions into the stream; recorded as
  an open question, not decided.
- Not the board. `sminos post` is group-scoped, long-form, and agent-to-agent
  durable record; the stream is human-directed and session-keyed.
- Not a heuristic filter over the transcript. A reader shows what the agent
  marked, nothing it guessed at; the point is that the agent decides.
- Not a transport. The human's replies go back over `SendMessage` (from a
  session) or `sminos send` (from a terminal or afleet) exactly as today.

## Acceptance

Observable when the build lands:

- Given a transcript containing `<to-human>` spans in assistant text, in a
  subagent's text, inside a tool result, and inside a user message, a §2
  reader yields exactly the assistant main-line spans, in order, each with
  the record's session id and timestamp.
- A span whose text was streamed as two text blocks of one assistant message
  yields one message.
- `sminos inbox` lists spans from every session file modified within the
  window, oldest first; `--session` narrows by full id, prefix, or name;
  `--group` narrows to sessions filling a seat in the group; `--since` widens
  the window; `-n` bounds the tail; `--json` prints one object per span with
  session, name, seat, ts, and text.
- Reading the same files twice returns the same spans; reading after a file
  grows returns only the new spans when the reader kept its offset.
- `output-styles/to-human.md` carries the one-sentence doctrine and the
  explanatory style, keeps the coding instructions, and nothing more about
  what to send; a session launched with `"outputStyle": "to-human"` in its
  settings shows the doctrine in its context, and a session launched without
  it does not.
- `tests/sminos/run-sminos-tests.sh` covers each point above against
  fabricated transcript files.
- afleet, given only §2, renders the per-session and all-sessions views
  without calling the CLI.

## Decision Log

- Decision: agent → human only; replies ride the existing paths. Rejected: a
  bidirectional "human seat" with its own inbox. The reverse direction
  already exists twice (`SendMessage`, `sminos send`); duplicating it buys
  nothing.
- Decision: the mark is a tag in the agent's own message. Rejected, after
  first being chosen: a CLI verb `sminos human "<text>"` appending to a
  dedicated `human.jsonl`. The verb cost a tool call and a turn each time,
  could be gated by permissions, landed only when the command ran rather
  than as the words streamed, and produced a second file that had to agree
  with the transcript. The tag costs nothing, streams, can appear mid-turn,
  and leaves the transcript as the one record. The dedicated file's one
  advantage — a schema sminos controls — is moot because the consumer must
  read the transcript anyway for the expand view.
- Decision: the tag is `<to-human>`. Rejected: `<human>` (a common word,
  and a turn label in some transcript formats), and a namespaced
  `<sminos-human>` (the mark belongs to the agent–human relationship, not to
  the tool that happens to read it). Distinctive enough that an agent's
  prose about humans never matches.
- Decision: provenance is structural — assistant-role, main-line text blocks
  only. Rejected: scanning whole lines for the tag. Tool results, user
  messages, and peer messages can quote anything; the role and block filter
  is what keeps a quoted tag from surfacing, and the transcript supplies both
  fields on every record.
- Decision: one scan, two views. The per-session view is the reader over one
  file; the all-sessions view is the same reader over every file. Rejected:
  a separate cross-session aggregate. It would be a cache of the same scan.
- Decision: no message kinds. Rejected by the human: a `kind` attribute
  (report, question, blocker, finding). Judgment belongs to the agent; a kind
  taxonomy is a list of what to send in disguise, and it hardens before
  anyone has watched agents use the stream. Failures observed later may
  reintroduce structure with evidence.
- Decision: every session is a source. Rejected: seats only. The human's
  interactive sessions are where much of the work happens, and they hold no
  seat; keying on session id with the seat as an optional join covers both.
- Decision: name and seat are read-time joins. Reversed from the CLI design,
  where they were write-time snapshots: the transcript carries neither, and
  its own `custom-title` / `agent-name` records already hold the name
  history, so a reader has what it needs without sminos writing anything.
- Decision: one-sentence doctrine. Rejected: a criteria list ("send
  decisions, completions, blockers, surprises"). The human's call, and
  consistent with this repo's rule that a constraint earns its place only
  against an observed failure.
- Decision: the doctrine travels as an output style, selected per launch.
  Rejected: the root or project CLAUDE.md — its premise ("your messages are
  not shown to the human") is false in a plain terminal session, and
  CLAUDE.md is unconditional, so every session would hear a false premise and
  show raw tags. Rejected: a SessionStart hook keyed on a launcher variable —
  conditional, but needs a script and settings machinery, and delivers
  context rather than prompt. Rejected: the sminos SKILL.md and spawn
  preamble alone — they reach only seats and only sessions that load the
  skill, while the doctrine is about the surface, not the fleet. An output
  style is the harness's own slot for shaping how the agent writes to the
  user, is chosen by one settings key so the launcher that owns the surface
  turns it on, re-injects after compaction, and ships with the plugin. The
  style declares `keep-coding-instructions: true` because a custom style
  otherwise replaces the harness's coding guidance (verified in 2.1.260), and
  it includes the explanatory-insights text because only one style is active
  at a time.
- Decision: earlier still, rejected: registering a `human` peer in the
  harness's peer registry with its own inbox socket so agents could use
  native `SendMessage(to: "human")`. Reading the harness binary (2.1.259)
  showed it would work — see Surprises — but it rests on undocumented
  internals, carries a bare string, and solves cross-session addressing,
  which is not the goal.
- Decision: deferred until afleet plumbs it; this spec is the durable record.
  Rejected: building `inbox` now. Nothing reads the stream yet, and an unread
  stream teaches nothing about the doctrine's failure modes.
- Decision: the spec lives with the provider (this repo), and afleet points
  at it when it plumbs the consumer.

## Surprises & Discoveries

- (2026-09-05, harness 2.1.259) The cross-session inbox is a documented-in-code
  protocol: the server logs an injection recipe — an optional
  `{"type":"auth","token":…}` line then `{"type":"user","message":{…}}` —
  and identifies senders by the connecting process's pid via
  `SO_PEERCRED`/`LOCAL_PEERPID`, never from the payload. A non-session
  sender (such as `sminos send`) therefore arrives as `from="unknown"`,
  which is why sminos puts the sender in the frame's first line. Peers are
  listed only when `kind` is interactive, a session id exists, the peer
  protocol is ≥ 1, and the record was updated within 24 hours. Recorded
  because it made the rejected "human peer" alternative credible, and
  because a future cross-session design may want it.
- (2026-09-05) A transcript record carries more than the message: `sessionId`,
  `timestamp`, `isSidechain`, and record types `custom-title` and
  `agent-name` that hold the session's naming history. That is what let the
  tag design drop every write path — the reader has provenance and identity
  from the file itself.
- (2026-09-05) The harness binary contains a generic tag-stripping regex
  (`<([a-z][\w-]*)(?:\s[^>]*)?>[\s\S]*?<\/\1>`). It appeared to act on
  user-side text, not assistant text, but whether an assistant message that
  is entirely one `<to-human>` block is displayed specially by the harness's
  own terminal is unverified — a five-minute probe when the build starts.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-09-05 — Design recorded from the grill in the sminos rename session;
  build deferred to afleet's plumbing work.
- 2026-09-05 — Mark changed from a CLI verb writing `human.jsonl` to a
  `<to-human>` tag in the agent's message, read from the transcript; name and
  seat became read-time joins; `sminos inbox` became a transcript reader.
  Decision Log records the reversal and its reasons.
- 2026-09-05 — The doctrine's carrier became the `to-human` output style,
  shipped in `output-styles/` and selected per launch; the style file lands
  with this revision (the reader does not).
