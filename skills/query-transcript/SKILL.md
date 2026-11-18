---
name: query-transcript
description: Use when investigating a past Claude Code session from its transcript — why it did something, what it knew and when, whether it followed a rule, what happened in a stretch too long to read whole — including a subagent's transcript.
---

# query-transcript

`query-transcript <session> "<query>"` (on the Bash PATH) puts a question to a
haiku that holds one segment of a session in its context, as the session held
it: the stretch between two compactions. `<session>` is a session id, a unique
prefix, or a transcript path (`agent-*.jsonl` included). `--help` has the flags.

```
query-transcript a45b97a3 --list                        # segments: number, time range, tokens at the end
query-transcript a45b97a3 --segment 3 "<query>"         # one segment (default: the last)
query-transcript a45b97a3 --until 2026-10-15T20:03Z "<query>"   # the context as it stood then
query-transcript a45b97a3 --all "<query>"               # every segment, each answered on its own
```

## Reading the answer

The answerer is a different model reading the visible record, not the session
speaking. The session's thinking is not in the transcript (a thinking block is
an encrypted signature, readable only by the model family that wrote it), so a
"why" answer is the answerer's inference from what the session said and did.
Weigh it as an investigator's reading backed by quotes, never as recovered
reasoning, and say so when you relay it.

Each blockquote in the answer is looked up in the record afterwards:

```
Quotes checked against the record:
  2026-10-15T20:05:19Z  notice  2118c6b1  "<task-id>abfb63cb3b678267d</task-id>"
  not found in the record  "<summary>3 background agents didn't finish before the previous session ended..."
via haiku · 212,642 in · 1,821 out · $0.11 · 18 s
```

A stamp gives the row's time, its kind (human, session, tool result, summary,
notice, peer message) and its uuid; `(+N more)` means the passage recurs. The
answer's own sense of order is unreliable; the stamps are the timeline. A quote
`not found in the record` is a paraphrase, a passage mixed with commentary, an
invention, or one of the notices
the replay itself appends (a tool call "interrupted", background work that
"didn't finish before the previous session ended"), which the session never
saw. Do not build on it.

## Asking well

- **A decision: cut before it** with `--until` (a time, or a stamp's uuid), so
  what came after cannot colour what it knew and weighed then.
- **Several questions about one stretch go in one query.** Each call re-reads
  the whole segment, uncached; a follow-up is worth its own call only when the
  first answer leaves a gap.
- **A whole session**: `--all` or `--segments A-B` ask each segment separately
  (6 at a time, `--jobs`) and print the answers in order, each under its time
  range; a segment without the answer says so. Combining them is your job.

## Cost

About $0.50 per million tokens of segment, so roughly $0.10 to $0.30 a
segment. A long session can be tens of segments: `--list` prints the total and
what `--all` would cost at most, and a multi-segment run states its ceiling on
stderr before any call. Start from the segment that matters.
