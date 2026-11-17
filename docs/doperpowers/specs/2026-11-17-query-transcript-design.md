# query-transcript: a question put to a past session's whole context

Design, 2026-11-17. Approved by the owner in the session that wrote it (the four
forks under Decisions); built from this document without a living spec (one
milestone, one builder).

## Purpose

A session diagnosing another session (why it did something, what it knew and
when, whether it followed a rule) reads the transcript in pieces: greps, windows,
a script over the JSONL. That reading is incomplete by construction, and the
transcript holds no thinking text to fall back on (11,444 thinking blocks in one
83-compaction session, 33 with any text; the rest are an encrypted signature).

`query-transcript` puts the question to a haiku that holds the whole stretch in
its context: one segment of the session, as the session itself held it, plus the
question. Any general question is in scope.

What it is not: a way to recover thinking. The API hands a thinking block only to
the models allowed to read it (for an Opus 5.5 block: Opus 5.5, Fable 5.2, Mythos
5.2) and drops it from any other model's request, so haiku sees what a reader of
the transcript could see, all of it at once. The answerer is therefore an
investigator of a record, not the session speaking for itself.

## Evidence (spike, 2026-11-17, haiku at high effort, 7 `claude -p` calls, $1.63)

| Stretch | Fork input | Time | Cost | Known-answer questions |
|---|---|---|---|---|
| segment 0 | 212k tokens | 49 s | $0.24 cached, $0.13 uncached | 5/5 |
| segment 1, cut two ways | 275k | 24 s, 32 s | $0.28 | same answers |
| segment 2 | 545k | 47 s | $0.56 cached | 6/6 |
| segment 0 cut mid-turn | 116k | 25 s | $0.06 uncached | correct |
| a subagent's transcript | 168k | 20 s | $0.09 uncached | correct |

- A copy of the transcript cut at a compaction boundary resumes under a new
  session id (`claude -p --resume <copy> --fork-session`), from any working
  directory whose project folder holds the copy.
- Copying from the segment's own boundary gives the same context as copying from
  the file's start (275,101 against 275,140 tokens).
- A copy cut in the middle of a turn resumes; so does a subagent's transcript
  once `"isSidechain":true` reads `false`.
- Haiku was right where the spike's own row-reading script was wrong (a task
  notification that arrived as a queued attachment, a row kind the script skipped).
- Weaknesses seen: positions ("early / middle / late") were wrong, since the
  context carries no timestamps; one answer slipped into the first person; and
  the resume appends notices the session never saw (a tool call "interrupted",
  background tasks "failed when the previous session ended"), which answers
  reported as part of the record.
- Cache writes at the 1-hour TTL double the price of a one-off question.
- `showThinkingSummaries` changes nothing headless (requests still go out with
  `display: "omitted"`).

Spike scripts, for reference: `~/.local/share/query-transcript-spike/`
(`seg.py`, `run.sh`, `spike2.py`).

## Decisions

The owner's (2026-11-17):

1. **Any general question**, reasons for a decision and "when did it know" included.
2. **Investigator with quoted evidence**, not the session in the first person.
3. **A segment plus an optional cut point** (`--until`), so a question about a
   decision is answered from the context as it stood then, without what came after.
4. **A separate CLI**, not a sminos subcommand and not an MCP tool.

Made without asking:

- The model is haiku at high effort, fixed (the owner's opening instruction); no
  flag changes it.
- The answerer gets no tools: today's repository is not the repository of that
  moment, and reading it would contaminate the answer.
- A whole-session question returns each segment's answer in order, labelled with
  its time range; the caller synthesizes. Synthesis is judgment, and the caller is
  the stronger model.
- Prompt caching is off: several questions about one stretch go in one query.
- Every quote in an answer is checked against the record by the tool, which
  stamps it with the row's time or marks it not found. This is the answer to the
  wrong positions and to any invented quote.
- It ships in the doperpowers plugin: the program in a skill's `scripts/`, a
  launcher in the plugin's root `bin/` (which the engine puts on every session's
  Bash PATH), and the skill as what tells a session the command exists.

## Interface

    query-transcript <session> "<query>" [--segment N | --segments A-B | --all] [--until T]
                                         [--jobs N] [--timeout S] [--json]
    query-transcript <session> --list

- `<session>`: a session id, a unique prefix of one, or a path to a transcript
  (`.jsonl`; a subagent's `agent-*.jsonl` included). Ids are looked for under
  every `projects/*/` of the config dir (`$CLAUDE_CONFIG_DIR`, else `~/.claude`).
  An ambiguous prefix lists its matches and exits.
- **Segments.** Segment 0 runs from the session's start to its first compaction;
  segment k from the k-th compaction (its summary included, as the session held
  it) to the next; the last one to the end of the file as it stands. Default: the
  last segment. `--list` prints each segment's number, time range, and tokens at
  its end (`compactMetadata.preTokens`; the last segment's from the last usage row).
- **`--until T`**: an ISO time or a row's uuid (or its unique prefix). The context
  ends with the last row at or before it. Without `--segment` it picks the segment
  that holds T. Not with `--segments` or `--all`.
- **Several segments** (`--segments`, `--all`): run `--jobs` at a time (default 6).
  Before any call, stderr gets the plan: how many segments, their summed tokens,
  and the cost ceiling at $0.50 per million. An answer that is exactly
  `nothing relevant` prints as one line.
- **Output**, per segment: a header (segment, time range), the answer, the checked
  quotes (each with its time and row kind, or `not found in the record`), and a
  usage line (`via haiku · input · output · cost · seconds`). `--json` gives the
  same as one object.
- **Exit**: 0 when every segment answered; 1 when any failed (its header carries
  the reason; the others still print); 2 on usage errors.

## Mechanism

1. Resolve the transcript; find the compaction boundaries (`type: system`,
   `subtype: compact_boundary`) in one pass, by byte offset. Rows are whole lines;
   a last line without a newline (a live session mid-write) is left out.
2. Copy the stretch (from the segment's boundary row, or the file's start for
   segment 0, to the next boundary or the cut) to
   `<config dir>/projects/<the work dir's project folder>/<new uuid>.jsonl`, with
   the session id replaced by the new uuid in every row and, for a subagent's
   transcript, the sidechain flag cleared. The work dir is the tool's own
   (`~/.cache/query-transcript/work`), so no project's session list or `CLAUDE.md`
   is involved.
3. Run, from the work dir, with `SMNS_INTERNAL=1` and `DISABLE_PROMPT_CACHING=1`:

       claude -p --resume <copy> --fork-session --session-id <fresh uuid> --safe-mode
              --no-session-persistence --model haiku --effort high --tools ""
              --output-format json <frame + query>

4. Delete the copy and any transcript the fork wrote, whatever the outcome; at
   start, delete copies in the work dir's project folder older than a day (a
   crashed run's).
5. Check the quotes: every blockquote of the answer, split at ellipses, whitespace
   normalized, is searched in the strings of the stretch's conversation rows
   (`user`, `assistant`, `attachment`, `system`; not the engine's request log
   rows, which duplicate them without a time). A found quote gets the row's
   timestamp and kind (human, session, tool result, summary, notice).

The frame (the investigator's instructions, ahead of the query) carries what the
spike showed it needs: the reader is not the model that worked, and that model's
reasoning was never recorded; do not continue the task; answer from the record,
in the third person; give evidence as verbatim blockquotes, one passage each;
separate what the record shows from inference; say when the record does not hold
the answer; and the closing notices of an interrupted tool call or of background
work that failed or stopped when "the previous session ended" were added by this
replay and were never seen by the session. For several segments it adds the
`nothing relevant` reply.

A stretch too large for the window fails in the fork; that segment reports the
failure and the rest go on.

## Tests

Unit tests with a stand-in `claude` on PATH (no model calls), in a CI gate:
segment discovery and numbering, the cut (boundary, `--until` by time and by
uuid, a partial last line), id resolution (prefix, ambiguity, path), the copy's
rewrite (session id, sidechain flag), the command line and environment handed to
`claude`, cleanup on success, failure and timeout, the quote check (found,
elided, not found), several segments (order, the collapsed reply, a failed
segment's exit code), `--list`, `--json`.

A live check outside the gates repeats the spike's known-answer questions on a
transcript the caller names.

## Not in this change

- **Replaying a decision on the model that made it** (cut just before it, generate
  the next turn again, several times): the stronger instrument for "why", at about
  $2 a sample on a 500k context. `--until` is its foundation. Whether a same-model
  replay keeps the conversation's thinking blocks is unmeasured.
- Sessions on another machine.

## As built (2026-11-17)

Where building departed from the text above, with the evidence:

- **No `nothing relevant` reply.** Offered to the segments of a multi-segment
  run, haiku gave it to every segment at once (8 output tokens, no thinking, in
  4 to 9 s), the segment holding the answer included; reworded and moved after
  the question, the same. Asked that segment alone, it answered with five
  checked quotes. Every segment now gets the single-segment prompt, and a
  segment without the answer says so in a sentence or two (a two-segment
  `--all`: 680 output tokens for the empty one).
- **The copy leaves out `cost-state` rows.** A resume adds their running total
  to the fork's `total_cost_usd`: a $0.13 call reported $199.01.
- **The last segment's tokens** come from the last assistant row with a nonzero
  usage: engine-made replies (a hook's) carry zeros.
- **A project folder that is a symlink to another** (a moved checkout) names the
  same transcript twice; ids resolve by the file's real path.
- **Quote stamps carry the row's uuid** (its first 8 characters in text), the
  handle `--until` takes for a cut at that row.
- **A segment includes the rows its compaction kept.** A boundary's
  `compactMetadata.preservedMessages` / `preservedSegment` name rows from
  before it (the last reply and its turn's closing rows; 2 to 3 rows on each of
  the 83 boundaries of the CI-opt session) that the resume puts back after the
  summary. The copy and the quote check start with them, then the boundary.
  This is the spike's 39-token gap between a copy from the boundary and one
  from the file's start.
- **`--until T` ends with the last row stamped at or before T in file order**,
  as written above, without assuming stamps rise in file order (they do not
  everywhere); the segment is the one whose compaction came last at or before T.
- **The quote check tolerates typographic quote marks only.** `*` and backticks
  are code as often as markup (`2 ** 3`, ``echo `id` ``), so a quote that drops
  them is reported not found.
