# The question sheet's published set

What a second repository reads of the question sheet, frozen at one revision of doperpowers (contracts X1, X2, X3,
X4 and X7 of MAWS's `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`; the execution plan
`docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md` in this repository, I1 to I7). Every file here is
written by `sminos/tests/sheet-contract.gen.py`, by hand from the composite's §4.2 and the plan's tables, never by
an implementation; `sminos/tests/test_sheet_contract.py` holds sminos to it. A change after the set is published is a
ruling of the composite's writer, and raises `version` in `MANIFEST.json`.

## Files

| path | what it is |
|---|---|
| `MANIFEST.json` | `{v, version, files: {path: sha256}, digest}`; `digest` is the SHA-256 of the lines `<sha256>  <path>\n` of every other file, sorted by path |
| `schema/state.schema.json` | a record's `state.json` (I2): structure, not the tool input's bounds |
| `schema/inbox-line.schema.json` | one line of `inbox.jsonl` (I3) |
| `schema/show.schema.json` | what `sminos sheet show --json` prints (I4) |
| `schema/delivery.schema.json` | the `<sheet-delivery>` block, terminal and steer form alike (I7) |
| `schema/surface.schema.json` | a surface's registration (composite §7) |
| `schema/tool-input.schema.json` | the tool's input (composite §2.1 with §1's limits), without descriptions |
| `examples/<name>/` | an envelope (`envelope.txt`) with the record it was composed from (`input/sheet/<session>/`) and `case.json` `{recipient, runner, tz}`; `terminal/` also has `steer.txt`; `split/then/` is the second envelope of `split`'s Send, composed from its record once the first envelope landed |
| `examples/surface.json` | a registration |
| `grammar/result.md` | the first line of a call's result: its grammar and the pattern a reader matches |
| `grammar/result.examples.json` | stored calls, `[{input, result, parsed}]` |
| `fixtures/<case>/` | one step of the record: `case.json` `{name, covers, session, now, event, verdicts}`, `before/` and `after/` (each a `$SMINOS_HOME`: `sheet/<session>/...`), `show.before.json`, `show.after.json` |

The schemas are JSON Schema 2020-12 held to `type`, `properties`, `required`, `additionalProperties`, `enum`,
`const`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`, `pattern`, `oneOf` and `$ref` into
the same file's `$defs` (lengths in code points); any validator takes them. A `pattern` is ECMA-262, as JSON Schema
says, with no flags: each is anchored `^...$` and `$` is the end of input, so a string with a newline after it does
not match. A Python reader matches the whole string (`re.fullmatch`, or `\Z` for `$`). A verdict, an outcome and
a closed question are discriminated shapes: each variant is a closed object with its own fields required, so a field
that belongs to another variant is refused.

## Reading the fixtures

- `event` is the step's input (I5) given inline; `now` is the step's clock, which stamps `at` and `acceptedAt`.
  `verdicts` is the verdict each key of the tail ends with.
- A side with no record has no directory: `before/` is absent where the step makes the record (`empty`,
  `imported-legacy`), and its `show.before.json` is `null` (`sminos sheet show` exits 3, `no sheet`).
- `after/` equals `before/` where the step changed nothing (`torn-tail`): nothing is replaced and `seq` stays.
- A reference's file exists nowhere (`/Users/me/...`), so a reader on any machine reads `changed: true`.

## Reading the examples

- `envelope.txt` holds the envelope exactly, with no newline after its block; `{HOME}` stands for the
  `$SMINOS_HOME` the composer runs with. Times are in the zone `case.json` names.
- An example's record holds what the composer reads; its inbox is left out.

## Readings fixed with the set

Where the plan's shapes left a choice, the set takes one, the same in the plan's interfaces:

- **Serialization** (I1). A JSON document of the set is Python's `json.dumps(obj, sort_keys=True, indent=1,
  ensure_ascii=False)` and a newline, and a step's output is compared after the same serialization. An inbox line
  is compact JSON, its keys in the order its writer gave them.
- **A fixture's clock** (I1). `case.json` carries `now`, the step's time, beside the five fields I1 lists.
- **Always present** (I2). `import` is always `{never, calls}` and `log` always `{next, owed, projects}`; `calls`
  is a list. An answer's outcome always carries `picks`, `text` and `images` (`[]`, `""`, `[]` when the line had
  none); a dismissal's carries none of the three, and its `revision` is the question's at the dismissal. A record
  a `start` makes has an empty `inbox.jsonl` beside `state.json`.
- **`Verdict.at`** (I2) is when the step gave the verdict, for every verdict. When a question closed is
  `closed[id].at`, which `show` prints.
- **Cuts.** The envelope's prose cuts "at N with `…`" as the first N characters and `…`. Every cut of data is the
  first N characters with no mark: `Closed.question` (200), the receipt's text (80), `Closed.answer` (2,000), and
  `show`'s pending question (2,000) and labels (200).
- **What an answer leaves** (I2, I12). `Closed.answer` and the `answered` event the log is owed hold I7's line
  after the id in its full-text form: the question, `→`, the labels and `Their text:`, with no asker and no times
  (those belong to a delivery). The log's is whole; `Closed.answer` is its first 2,000 characters. `receipt` is
  written for an answered question only. A closed question keeps the `key` of the line that closed it.
- **A `delivered` line** (I2) sets `closed[id].deliveredAt` for each key it takes out of `pending`, as `landed`
  does. Only an answered or a dismissed question has a `deliveredAt`: a withdrawal is delivered to nobody (U5).
- **`sent`** (I4) lists the keys with a verdict, sorted by key, then the queued lines in inbox order. A queued
  retract carries its `target`. A `delivered` line's own key reads `delivered` (verdict `applied`, never pending).
- **A line a reader drops** (I4) is one a drain skips (U2): it is not JSON (NaN and the infinities are not), it
  fails the line's schema, a string in it holds a lone UTF-16 surrogate, or it answers an open question at its
  current revision with a pick that is no label of it, or with two picks on a single-select question.
- **The door** (I3) refuses each of those it can see, exit 2 with nothing appended. An upload's name is at most 250
  characters. Its one `write`, should it come back short, is completed while the lock is held; a write the file
  refuses is cut back to the file's length before the call, and the door exits 1 with nothing appended.
- **Picks by place** (I2, I4). A closed answered question keeps `places`, its picks as integers from 1 among the
  options of the answered revision, as the block carries them. `show --json` carries `places` on each pending answer
  too, read from the whole snapshot before any label is cut: two imported labels can share their first 200
  characters (the `imported` example's do). The cut labels stay beside them for display; the inbox line keeps
  labels.
- **A reader that cannot pair** (I4). The reader reads `state.json`, the inbox, `state.json` again, at most four
  times; if `seq` moved every time it returns nothing unverified: `sminos sheet show` exits 75, and a reader reads
  again.
- **Cuts in `show`'s pending outcomes** (I4), in both forms: the question at 2,000 characters, its header at 60,
  each label and each pick at 200, a subagent's name at 200. An agent id is at most 128 characters, a bound of this
  contract (the engine's ids are far shorter), and is never cut; nor is a question's id, which is at most
  `q999999999`.
- **No record** (I4). `show` exits 3 (`no sheet`); a fixture writes that as `null`.
- **The keyed form** (I4). `show --json --keys` (at most 50 keys) carries each pending outcome under the cuts
  above and its `text` as its first 500 characters, with `textCut: true` when it was longer and the record's
  `textFile` where it has one: every string it carries is bounded, and a hook reads it through a process call that
  returns at most 4 MiB. The unkeyed form carries texts whole.
- **A start's asks** (I5), inline or staged: `{callId, askedAt, questions}`, `questions` today's tool's objects as
  it held them.
- **The input schema** (I6) states neither the call's two rules nor an entry's own (U14): a preview on a
  multi-select question passes the schema and is refused by the entry check, alone.
- **Inside an envelope** (I7), `answered` and `dismissed` each list their questions by the id's number (q8 before
  q12). Which outcomes an envelope carries is the packing's; their order is the ids'.
- **The block** (I7) places `textCut` and `textFile` after `text`, and `more` after `dismissed`, each present only
  when true or when the text has a file.

## Pinning

MAWS copies this directory whole into its tree beside a provenance note naming the doperpowers merge commit, the
sminos version and `digest`, and recomputes the digest over its copy.
