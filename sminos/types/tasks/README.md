# The Task Board's published set

What a second repository reads of the Task Board, frozen at one revision of doperpowers (contracts X1, X2, X3 and
X6 of `docs/doperpowers/specs/2026-11-27-task-board-design.md`; its child B1's execution document
`docs/doperpowers/plans/2026-11-27-task-board-b1.md`, §1 to §3 and §5, gate G1). Every file here is written by
`sminos/tests/tasks-contract.gen.py`, by hand from those documents, never by an implementation;
`sminos/tests/test_tasks_contract.py` holds sminos to it. A change after the set is published is a ruling of the
composite's writer, and raises `version` in `MANIFEST.json`.

## Files

| path | what it is |
|---|---|
| `MANIFEST.json` | `{v, version, files: {path: sha256}, digest}`; `digest` is the SHA-256 of the lines `<sha256>  <path>\n` of every other file, sorted by path |
| `schema/state.schema.json` | the store, `$SMINOS_HOME/tasks/state.json` (§1) |
| `schema/act-line.schema.json` | one line of the door, `sminos task act` (§3) |
| `schema/verdict.schema.json` | one verdict the door prints, and `applied[key].verdict` (§3) |
| `schema/list.schema.json`, `show.schema.json`, `waiting.schema.json` | the readers' `--json` (§3) |
| `examples/state.json` | a store holding an outcome for each value of `send` and a verdict for each `told` |
| `examples/lines.json`, `verdicts.json`, `list.json`, `show.json`, `waiting.json` | one of each shape |
| `grammar/texts.md` | the notice, the ended line, the start line and what `remind` prints: their grammar and the pattern a reader matches |
| `grammar/texts.examples.json` | each form with the fields it was built from |
| `fixtures/<case>/` | one step: `case.json` `{name, covers, now, session, argv, stdin, exit, stdout, stderr}`, `before/` and `after/` (each a `$SMINOS_HOME`) |

The schemas are JSON Schema 2020-12 held to the question sheet's subset (`type`, `properties`, `required`,
`additionalProperties`, `enum`, `const`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`,
`pattern`, `oneOf`, `$ref` into the same file's `$defs`; lengths in code points); a `pattern` is ECMA-262 with no
flags, anchored `^...$`, `$` the end of input. The store's objects leave `additionalProperties` unstated: every
writer keeps a field it does not know (D3), so a later version's field is no error. A line, a verdict, a target and
a reader's `waiting` row are closed; a line with a field its act does not list is refused.

## Reading the fixtures

- `argv` follows `sminos`; `session` is the caller's `CLAUDE_CODE_SESSION_ID` (null: none, a terminal that is no
  session); `stdin` what the command reads (null: nothing); `now` the step's clock, which stamps every `at`.
- A side with no store has no `tasks/state.json`: `before/` lacks it where the step makes the store.
- `before/` and `after/` are a `$SMINOS_HOME` each, with the thread records the step reads (`threads/<id>.json`),
  which no step changes. A replay runs with that home, a `HOME` of its own with no engine records (no process holds
  any session) and the fixture's clock, and compares `tasks/state.json` after reading and serializing it again.
- `after/` equals `before/` where the step changed nothing: nothing is replaced and `seq` stays.

## Readings fixed with the set

- **Serialization.** A JSON document of the set is Python's `json.dumps(obj, sort_keys=True, indent=1,
  ensure_ascii=False)` and a newline. A line and a verdict are printed compact, their keys in §3's order.
- **Always present.** Every field of §1 is on every task and outcome, null where it has no value: `due`,
  `project`, `alias`, `agent`, `closed`, `shown`, `send`, `endedLine`. `body` is `""` when none was given, `tags`
  `[]`. An agent's `name` is null when none was given. An outcome's `text` is the note, the reason or the
  comment, `""` for a done with no note.
- **A new task** has `agentSeq` and `seenSeq` both at its `born`: it is not Updated.
- **Every applied line is kept by its key**, `seen` and `shown` too, and is one change of the store (`seq` + 1)
  even where it changed nothing else. A verdict that is not `applied` (stale, closed, unknown, refused) is not
  kept and changes nothing; the same line again is judged again.
- **The order of the refusals.** A key already used comes first (the stored verdict, or `key-reused`); then an
  unknown id; then a task no longer open (`closed`); then a revision that is not current (`stale`).
- **`seen`** raises `seenSeq` to the line's `seq`, never lowers it, and never past the store's `seq` before the
  step.
- **An outcome's `revision`** is the task's at the act; its key is `<id>.<acts>`, `acts` counted after the act.
- **A comment's `n`** counts the task's comments from 1, the human's and the agents' alike. The human's names its
  outcome; an agent's has `outcome: null`.
- **`wake`** is resolved at the act: the line's when it is not null, else whether the task is blocking.
- **Until M2** every outcome is written with `send: null` and `endedLine: null`, and `told` is `next-start` but for
  `ended` and `maws`; the schemas carry every value M2 fills (`examples/state.json`).
- **The readers.** `list --json` gives the tasks in the order of their ids' numbers, `waiting --json` the outcomes
  by `seq`; the text forms order as §3 says. `list --closed` is the closed tasks whose `closed.at` is within 30
  days, `--all` those and the open ones.
- **What `remind` prints** is `grammar/texts.md`'s `remind`: the keys line is empty when nothing waits, and a
  start line with neither part prints nothing after it.

## Pinning

A consumer copies this directory whole into its tree beside a provenance note naming the doperpowers merge commit,
the sminos version and `digest`, and recomputes the digest over its copy.
