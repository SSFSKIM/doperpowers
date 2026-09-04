# The Human Stream — Design

A Claude Code session's transcript is two things at once: the agent's working
record (every tool call, every intermediate thought) and the only surface the
human has for reading what the agent is doing. This design separates them. An
agent decides for itself which words the human should read and sends those,
and only those, through `sminos human`; the human reads that stream — for one
session, or for every session at once — and opens the transcript only when
they want to look inside. The transcript becomes a log; the stream becomes
the conversation.

This is plumbing for a consumer that does not exist yet: `afleet`
(`~/Developer/GitHub/afleet`), a GUI workspace for coding agents whose default
view is the agents' reports to the human, with the full transcript folded
behind a click. sminos is the provider, afleet the consumer, and the record
format in §2 is the contract between them. Nothing here is built now; this
document records the decisions so that the build, when it comes, does not
re-derive them.

Human-confirmed frame (2026-09-05): direction is agent → human only (the
human's replies ride the existing `SendMessage` and `sminos send`); one
global log with the per-session view as a filter over it; no message kinds;
every session is a source, seats and seatless interactive sessions alike; the
agent-facing instruction is one sentence, with no list of what to send or
withhold; deferred until afleet plumbs it.

## §1 The agent's side

One verb, one sentence of doctrine.

    sminos human "<what the human should read>"     # body via stdin for long text

The sender is the calling session, read from `CLAUDE_CODE_SESSION_ID` the way
`sminos status` and `sminos post` already read it. From a plain terminal with
no session id the verb refuses (exit 2): the stream is agent-to-human by
definition, and the operator has no reason to write to themselves. Tests set
the variable.

The doctrine, carried by the sminos SKILL.md protocol and the spawn preamble,
is one sentence: *your tool results and messages are not shown to the human;
what the human should read goes through `sminos human`.* No kinds, no
criteria, no cadence. The judgment of what a human needs to hear is the
agent's, and it is expected to be good; if observed failures show otherwise,
the doctrine is refined from those failures, not from anticipation.

Consequence worth stating: an agent's closing message of a turn is also not
shown in afleet's default view, so an agent that wants the human to see its
summary sends it through the stream too. The one sentence covers this without
saying it.

## §2 The record — the contract with afleet

One append-only file under the registry root, one line per message:

    $SMINOS_HOME/human.jsonl

    {"id": 41, "ts": "2026-09-05T03:12:08Z",
     "session": "30e0568a-f1ee-4dce-8db9-b9799fb23107", "name": "sminos-guide",
     "seat": "demo/scout", "cwd": "/Users/new/Developer/GitHub/doperpowers",
     "text": "…"}

- `id` — monotonic across the file, assigned under the registry lock the way
  board post ids are.
- `ts` — UTC, second resolution, the CLI's usual format.
- `session` — the sender's full session id; the key both views filter on.
- `name` — the harness session name at write time, from the peer registry
  (the `name` field of `~/.claude/sessions/<pid>.json` whose `sessionId`
  matches); empty when the session has no live record.
- `seat` — `group/alias` when a seat's `current` is this session; empty for a
  seatless session. Recorded so a group view needs no join.
- `cwd` — the sender's working directory, as board posts record it.
- `text` — the body, verbatim.

`name` and `seat` are snapshots, not references: names change and seats are
refilled, and the record says what was true when the human was addressed.

Writes are single-line appends under the shared registry flock (`.metalock`),
so any number of sessions may write concurrently. The file is created 0600
inside the 0700 root; its content is agent-authored prose addressed to the
operator, never a credential. No rotation or retention in the first cut; a
consumer that wants a window filters by `ts` or `id`.

afleet reads this file directly — tail it, split by `session` — and needs
nothing else from sminos to render the default view. The CLI below is for a
human at a terminal and for tests; it is not the contract.

## §3 The human's side

    sminos inbox                          # every session, oldest first, newest last
    sminos inbox --session <id|prefix|name>
    sminos inbox --group <group>          # messages whose seat is in the group
    sminos inbox -n 20                    # the last N
    sminos inbox --json                   # the records as written

`--session` resolves a full id, an id prefix, or a harness session name (the
`name` snapshot in the records). Text output shows `ts · name (seat) · text`,
one message per block, in the board's rendering habits. `--json` prints the
lines unchanged.

`sminos tui` may later show the focused seat's recent stream in its panel and
grow a fleet-wide inbox view; that is a possible slice, not a commitment of
this design — afleet is the intended reading surface.

## §4 What this is not

- Not a replacement for `status` (the one-line "what I am doing now"),
  `reply` (a turn's final answer), or the pending-question rendering of a
  blocked seat. Those describe state; the stream is the agent addressing the
  human. A later cut may fold pending questions into the stream; recorded as
  an open question, not decided.
- Not the board. `sminos post` is group-scoped, long-form, and agent-to-agent
  durable record; the stream is human-directed and session-keyed.
- Not a filter over the transcript. Deriving a human view from the transcript
  by heuristics is exactly the post-hoc guessing this design removes; the
  point is that the agent decides.
- Not a transport. The human's replies go back over `SendMessage` (from a
  session) or `sminos send` (from a terminal or afleet) exactly as today.

## Acceptance

Observable when the build lands:

- Inside a Claude session, `sminos human "x"` appends one record whose
  `session` is that session's id, whose `name` is its harness name, and whose
  `seat` is `group/alias` when the session fills a seat and empty otherwise.
- Long text arrives intact through stdin.
- From a terminal without `CLAUDE_CODE_SESSION_ID`, `sminos human` exits 2 and
  says the stream is written by sessions.
- `sminos inbox` lists records from every session, oldest first; `--session`
  narrows by full id, prefix, or name; `--group` narrows by seat group;
  `-n` bounds the tail; `--json` prints the lines as written.
- Two sessions writing concurrently produce a file every line of which parses,
  with ids strictly increasing.
- The sminos SKILL.md protocol and `references/spawn-preamble.md` each carry
  the one-sentence doctrine and nothing more about what to send.
- `tests/sminos/run-sminos-tests.sh` covers each point above with the
  CLI driven under a fabricated `CLAUDE_CODE_SESSION_ID` and peer record.
- afleet, given only the path of `human.jsonl` and §2, can render the
  per-session and all-sessions views without calling the CLI.

## Decision Log

- Decision: agent → human only; replies ride the existing paths. Rejected: a
  bidirectional "human seat" with its own inbox. The reverse direction
  already exists twice (`SendMessage`, `sminos send`); duplicating it buys
  nothing.
- Decision: the agent writes through the sminos CLI. Rejected: registering a
  `human` peer in the harness's peer registry (`~/.claude/sessions/`) with its
  own inbox socket so agents could use native `SendMessage(to: "human")`.
  Reading the harness binary (2.1.259) showed this would work — the peer
  protocol is newline-delimited JSON on a `/tmp/cc-socks/<pid>.sock` socket,
  auth off by default, sender identified by the kernel-reported peer pid — but
  it rests on undocumented internals that shift between releases, carries a
  bare string, and solves cross-session addressing, which is not the goal.
  The CLI path identifies the sending session for free, can record name and
  seat, and depends on nothing outside sminos.
- Decision: one global log; the per-session view is a filter. Rejected:
  per-session files. The all-sessions view would then be a merge over many
  files, and afleet would have to watch a directory instead of tailing one
  file. Both views over one file are the same code with a predicate.
- Decision: no message kinds. Rejected by the human: a `kind` field
  (report, question, blocker, finding). Judgment belongs to the agent; a kind
  taxonomy is a list of what to send in disguise, and it hardens before
  anyone has watched agents use the stream. Failures observed later may
  reintroduce structure with evidence.
- Decision: every session is a source. Rejected: seats only. The human's
  interactive sessions are where much of the work happens, and they hold no
  seat; keying on session id with the seat as an optional snapshot covers
  both.
- Decision: `name` and `seat` are snapshots taken at write time. Rejected:
  resolving them at read time. A read-time join gives the current name for a
  past message and loses the seat once it is refilled; the record should say
  who spoke.
- Decision: one-sentence doctrine, in SKILL.md and the preamble. Rejected: a
  criteria list ("send decisions, completions, blockers, surprises"). The
  human's call, and consistent with this repo's rule that a constraint earns
  its place only against an observed failure.
- Decision: deferred until afleet plumbs it; this spec is the durable record.
  Rejected: building the CLI now. Nothing reads the stream yet, and an unread
  stream teaches nothing about the doctrine's failure modes.
- Decision: the spec lives with the provider (this repo), and afleet points
  at it when it plumbs the consumer. The contract belongs where the format is
  produced.

## Surprises & Discoveries

- (2026-09-05, harness 2.1.259) The cross-session inbox is a documented-in-code
  protocol: the server logs an injection recipe — an optional
  `{"type":"auth","token":…}` line then `{"type":"user","message":{…}}` —
  and identifies senders by the connecting process's pid via
  `SO_PEERCRED`/`LOCAL_PEERPID`, never from the payload. A non-session
  sender (such as `sminos send`) therefore arrives as `from="unknown"`,
  which is why sminos puts the sender in the frame's first line. Peers are
  listed only when `kind` is interactive, a session id exists, the peer
  protocol is ≥ 1, and the record was updated within 24 hours. Recorded here
  because it is what made the rejected "human peer" alternative credible, and
  because a future cross-session design may want it.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-09-05 — Design recorded from the grill in the sminos rename session;
  build deferred to afleet's plumbing work.
