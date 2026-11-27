# Question sheet C2, M1: the report

This covers milestone M1 of `docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md`: the contracts,
published, which is the composite's G1. It was built on branch `question-sheet-c2`, from the plan at `198dff493`.

## Status

DONE. The pull request is open and not merged; the high-rung review and the merge belong to the dispatching
session. M1's line in Progress is not ticked. Once the PR merges, that line is completed with the merge commit, the
sminos version (1.57.0) and the digest.

## Commits

- `b5ef06522` the published set, plus `sminos sheet put` and `show`
- `0da0c43d2` `log.next` now counts the events earlier steps already owed the log
- `2f037d035` the task review's fixes and the two rulings (a sixth example, `split`; the keyed form's 500-character cut)
- the commit that adds this report

## The generator's line

    sheet-contract: 21 cases, 6 examples, digest 90af4aeca2a96c5d2fe3a431c289548a6d502f970f0fde4925f119fdda9ba151

## Gates

I ran `ci-gate --gates sminos,sminos-suites-c,version-bump,shell-lint` on `2f037d035`. It came back GREEN:
https://github.com/SSFSKIM/doperpowers/actions/runs/45346758942 (version-bump, shell-lint, sminos in 10m05s,
sminos-suites-c in 12m33s). The first head, `b5ef06522`, was also GREEN (run 45345411656). The fix wave's gates are
under "Fix wave 1".

Locally, `sheet-contract.gen.py --check` passes and `test_sheet_contract.py` ends `test_sheet_contract: 34 passed`.

## The by-hand demo (Concrete Steps, M1)

    $ export SMINOS_HOME="$(mktemp -d /tmp/sheet.XXXXXX)"
    $ cp -R sminos/types/sheet/fixtures/references/before/sheet "$SMINOS_HOME/"
    $ S=5eed0000-0000-4000-8000-000000000019
    $ sminos sheet show --session "$S"
    q1  Session check
      Is the session check in these lines the one to keep?
      1. Yes  (recommended)
      2. No
      file: src/auth.ts:40-80  (changed since asked)
      file: README.md  (changed since asked)
      file: docs/login.png  (changed since asked)

    q2  Migration
      Ship the migration today?
      1. Yes  (recommended)
      2. No
      queued (cli-1901a001): Yes
    $ printf '%s\n' '{"v":1,"key":"demo-0001","kind":"dismiss","id":"q1","by":"cli"}' | sminos sheet put --session "$S"
    {"session": "5eed0000-0000-4000-8000-000000000019", "results": [{"key": "demo-0001", "state": "queued"}]}
    $ sminos sheet show --session "$S"
    q2  Migration
      Ship the migration today?
      1. Yes  (recommended)
      2. No
      queued (cli-1901a001): Yes

    dismissed, not yet applied: q1

## Decisions the plan did not carry

The dispatching session accepted each of these. Each one is written in two places, in the same words: the set's
`README.md` (section "Readings fixed with the set") and the plan's interface it belongs to.

1. A fixture's `case.json` carries `now`, the step's clock (I1).
2. Serialization: every JSON document of the set is `json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False)`
   plus a newline, and a step's output is compared after the same serialization (I1). An inbox line is compact JSON,
   with its keys in the order its writer gave them.
3. `Verdict.at` is when the step gave the verdict, for every verdict. When a question closed is `closed[id].at`
   (I2).
4. Inside an envelope, `answered` and `dismissed` each list their questions by the id's number (q8 before q12) (I7).
   I7's own terminal example forces this: q8 does not wake the session, yet it stands between q7 and q12, which do.
5. Cuts.
   - The envelope's prose: "cut at N with `…`" means the first N characters followed by `…`.
   - Every cut of data is the first N characters with no mark: `Closed.question` (200), the receipt's text (80),
     `Closed.answer` (2,000), and show's pending question (2,000) and labels (200).
6. What an answer leaves (I2).
   - `Closed.answer` and the log's `answered` text hold I7's line after the id in its full-text form, without the
     asker and without the times. The log keeps it whole; `Closed.answer` cuts it to 2,000 characters.
   - A receipt is written only for an answered question.
   - A closed question keeps the key of the line that closed it.
7. A `delivered` line sets `closed[id].deliveredAt`, as `landed` does (I2).
8. `sent` (I4).
   - It lists the keys with a verdict, sorted by key, then the queued lines in inbox order.
   - A queued retract carries its `target`.
   - A `delivered` line's own key reads `delivered`.
9. Fields that are always present (I2).
   - Every record has `import {never, calls}` and `log {next, owed, projects}`.
   - An answer's outcome always carries `picks`, `text` and `images`; a dismissal's outcome carries none of the three.
   - A dismissal's `revision` is the question's revision at the dismissal.
   - A record that a `start` makes has an empty `inbox.jsonl` beside `state.json`.
10. No record: `show` exits 3 (`no sheet`), and a fixture writes that as `null` (I4).
11. The tool-input schema states neither the call's two rules nor an entry's own rules (U14). The line range's
    bounds are among the entry rules (I6).
12. A start's ask, staged or inline, has the shape `{callId, askedAt, questions}` (I5).
13. The block places `textCut` and `textFile` after `text`, and `more` after `dismissed`. Each is present only when
    it holds (I7).
14. Two rulings on points the task review raised, written into I4, I7 and M1:
    - A sixth example, `split`: one Send of forty answers of exactly 2,000 characters. The first envelope carries
      twenty-two, with `More follows.` and `"more": true`. The second carries the other eighteen; it is in
      `split/then/`, composed from the record once the first had landed.
    - The keyed form, `show --json --keys`, holds each pending text to its first 500 characters with `textCut`.

### Smaller choices of my own, not frozen shapes

- The door's `batch` is a 32-character hex uuid. On a call of several lines it overwrites any batch the caller gave.
- The door refuses two picks on a single-select question, as I3 says. A line like that which did not come through
  the door is invalid and is skipped: the fix wave added the case to U2's list.
- If the door's one `write` comes back short, the rest is written while the lock is held. If the file refuses more,
  it is cut back to its length before the call, and `put` exits 1 with nothing appended (fix wave, finding 1).
- `show`'s text form is the block M1's decisions describe, plus two footers: `dismissed, not yet applied:` and
  `accepted, not yet delivered:`.
- `bridge_standin.py` gained `results` (`{op: result}`), for an op the stand-in answers at once.

## Ambiguities met in the frozen shapes

- I4 says a `closed` verdict carries "how and when", but a Verdict has only one `at` (resolved by decision 3).
- I2's receipt rule says "none for withdrawn", which would give a dismissal a receipt of an empty text. I read it as
  no receipt (decision 6).
- I4's rule "`delivered` (verdict applied, not in pending)" applied literally to a `delivered` line's own key
  (decision 8).
- I4's "says nothing of its target", for a queued retract, I read as "makes no entry for the target". The retract's
  own entry still carries `target`.
- The composite's G1 asks for "a Send in two parts", and the plan's five examples held none. Ruled: the `split`
  example.
- I4's "a few kilobytes an outcome" does not hold for a keyed outcome at the line's bounds. Ruled: the 500-character
  cut.

## The task review

One task review (doperpowers:task-reviewer) covered `198dff493..0da0c43d2`. It found nothing Critical, eleven
Important findings and two Minor ones. All of them are fixed in `2f037d035`, two by way of the rulings above. None
was deferred, so the PR has no Unresolved Review Findings section.

## Environment

Nothing blocked the work. `ci-gate` ran twice on GitHub Actions, GREEN both times.

## Fix wave 1: the high-rung review of #628

The review (`~/.local/share/question-sheet/c2-m1-codereview-1.md`) returned eleven findings with the verdict
"incorrect". I checked each against the code, found all eleven true, and fixed them in `7139891f9`, following the
coordinator's rulings on the ones that touch a frozen shape. A task review of that commit found four Important and
two Minor findings; all six are fixed in `4c43641b9`. Every frozen-shape change is in the set's README and in the
plan's interfaces (I1 to I4, and U2), in the same words. The manifest's `version` stays 1.

1. **A short write committed half a Send.** A short `write` is now completed while the lock is still held. A write
   the file refuses is cut back to the file's length before the call; `put` exits 1 with nothing appended. Tests:
   a short write is completed, with a probe confirming the lock is held throughout; a failure after a whole first
   line restores the file byte for byte. Both are tested separately from a killed writer.
2. **A pick lost its option after labels were cut.** A pick now travels as its place. The record's `Closed` holds
   `places`. `show --json` carries `places` on each pending answer, read from the whole snapshot before any label
   is cut, and on each closed answered question. The `imported` example now has two labels that share their first
   200 characters; the pick is place 3, pinned in the block, in show's pending outcome and in show's closed entry.
3. **The reader could return an unverified pair.** It now returns only a verified pair. On sustained contention
   `show` exits 75 and a reader reads again (stated in the README and in I4).
4. **The keyed form was unbounded.** Every string in a pending outcome is cut: the question at 2,000, the header at
   60, labels and picks at 200, a subagent's name at 200, and in the keyed form the text at 500. An agent id is
   at most 128 characters (a bound of this contract) and a question id at most `q999999999`; neither is ever cut.
   Tested with picks, headers, labels and names of 87,000 four-byte characters, and with `sent` included: under
   2 MiB for 50 keys.
5. **Non-finite numbers aborted the reader.** NaN and the infinities are not JSON: the door refuses them with exit
   2, and the reader skips them. A value nested past the decoder is handled the same way. Tested with a bad line
   followed by a good one.
6. **Patterns disagreed at the end of a string.** Patterns now match the whole string, in the door and in the
   suite's validator, with ECMA-262's end of input. The README states the dialect.
7. **Lone surrogates.** The door refuses them with exit 2, and the reader skips them under U2, as stated in I3 and
   the README. `skipped-and-unknown` now pins both new U2 cases (six lines skipped).
8. **SKILL.md's recipe reused one key.** It now makes a new key for each new act and says when to reuse one.
9. **Verdicts.** They are now discriminated shapes, one per (verdict, kind) pair with its own fields required.
   Negative tests cover each missing field, an `unseen` verdict that reads `applied` or has an `id`, and a
   `delivered` line's own key reading `accepted`.
10. **Outcomes.** They are now discriminated shapes too; a dismissal carrying `picks`, `text` or `images` is refused.
    Closed questions are discriminated as well, and a withdrawal has no `deliveredAt`.
11. **`split` broke the 32-answer rule.** It now keeps the answer line only on the 32 questions answered last, in
    both of its records.

U2's list also gains two picks on a single-select question, at an equal revision.

Generator line after the wave:

    sheet-contract: 21 cases, 6 examples, digest 550b09dce06dc54dd3c6413a5360a37fc87ab12819cac46c65e5ec732f9dddd4

Tests: `test_sheet_contract: 38 passed`.

Gates: `ci-gate --gates sminos,sminos-suites-c,version-bump,shell-lint` ran GREEN on `4c43641b9`,
https://github.com/SSFSKIM/doperpowers/actions/runs/45351655242. The intermediate head `7139891f9` was GREEN too (run
45350746456).

## Fix wave 2: the high-rung review's second pass

The branch first took current main (`e32649e88`, a clean merge). origin/main carries sminos 1.56.0 and the branch
1.57.0, so the version bump needed nothing. The fixes are in `bd3cf9d55`.

1. **A lock-free reader can see a short write's first lines before the rest or the rollback.** Not repaired, as
   ruled. Logged as `docs/doperpowers/TECH-DEBT.md` row #37 (T3). The plan's I3 names it, and so do its M7 limits
   list and the README's door reading.
2. **A Python validator reads a pattern's `$` more loosely than ECMA-262 does.** Not repaired, as ruled. Logged as
   TECH-DEBT row #38 (T3). The plan's I1 dialect paragraph names it, and so do M7's list and the README's dialect
   paragraph.
3. **A lone surrogate in a record's string made `show` fail.** `printable()` in `sminos_sheet.py` now writes every
   lone surrogate as U+FFFD before `show` prints, in both the JSON and the text form. A test plants one in a label
   and checks that both forms exit 0, that U+FFFD stands in its place, and that the output passes the show schema.
   The writer rule is now in the plan:
   - U14 lists a lone surrogate as one of an entry's own refusals;
   - M2's import replaces each lone surrogate with U+FFFD;
   - I4 states the reader's rule and the writers' side.
   
   The README says the same.
4. **Queued `sent` entries are now discriminated by kind.** An answer or dismissal requires `id` and may carry
   `cancelled`; a retract requires `target`; a `delivered` line has neither. Negative tests cover:
   - a retract carrying `id` or `cancelled`;
   - a retract without `target`;
   - an answer carrying `target`;
   - a delivered line carrying `id`.
5. **The show schema has its own string limits.** `cutSnapshot` and `cutAsker` set the bounds: header 60,
   question 2,000, labels and picks 200, a subagent's name 200. A pending outcome's text is at most 20,000
   characters. The state schema still bounds nothing. Tests check that an over-long header, question or pick fails
   the show schema, and that the state schema accepts a long imported question.
6. **The handle's pattern** is now `^q[1-9][0-9]{0,8}(@[1-9][0-9]*)?$`, which bounds the id and leaves the
   revision open.
7. **An upload's name.** The README and the plan's I3 now say that the stem before the final dot is 1 to 250
   characters. The door's error message says the same.

Generator line:

    sheet-contract: 21 cases, 6 examples, digest 594200ae4e539c0688c67b511968861d8ebf03c87d1c45b512903a538326e277

Tests: `--check` passes; `test_sheet_contract: 39 passed`; pyflakes is clean. The diff contains no path under the owner's home.

Gates: `ci-gate --gates sminos,sminos-suites-c,version-bump,shell-lint` was GREEN on `bd3cf9d55`, run
https://github.com/SSFSKIM/doperpowers/actions/runs/45355494591. Timings: version-bump 0m07s, shell-lint 0m24s,
sminos 7m54s, sminos-suites-c 12m47s.

# Question sheet C2, M2 to M7: the report

This covers milestones M2 to M7 of the same plan, run through subagent-driven execution: one executor per milestone,
a task review after each, fixes resumed on the executor, the plan kept current by the controller between them. Branch
`question-sheet-c2`, from `b5b91b50e` (M1 merged as `2594002af`).

## Status

DONE. One pull request for M2 to M7, ready for review, not merged. The whole-branch review and the merge are the
dispatching session's. `sminos/types/sheet/` is untouched since M1 and the generator prints what M1 published
(`sheet-contract: 21 cases, 6 examples, digest 594200ae…`). Sminos goes from 1.58.0 to 1.59.0, once.

## Commits, per milestone

| Milestone | Build | Fix waves | Gates |
|---|---|---|---|
| M2 the record | `97218983c`, `09b485a94` | `17c2827c2`, `b204a4e56` | GREEN, run 45375809111 |
| M3 asking | `63c6ba718`, `7ea4a11ed` | `9a75c18c2`, `586d91dc2`, `8236347a1` | GREEN, run 45397387138 |
| M4 delivering | `448e8540e`, `e4ff0d9e1` | `eb5009c7e`, `53d2ce750`, `55ada7748`, `cfdbd4914`, `080859bc2` | (covered by M5's) |
| M5 drawing, import | `43a2f66f8`, `989f3f836` | `9e16956d3`, `b65335160`, `61394a6e3`, `69d0590f2` | GREEN, run 45456729517 |
| M6 readers, end of life | `e11ecf907` | `87b3e5e93`, `35936fe3e`, `d34ebdde8`, `5c0c26b7a`, `e11c4922c` | GREEN, run 46041678823 |
| M7 manuals, acceptance | `c0c6d74a9` | `4d9192979` | GREEN 24/24, run 46047674138 |

Then main merged in (`a904492ed`; one conflict, the `hooks.json` description, resolved keeping both sides' sentences)
and the version bump (`f645070ac`). Plan commits between them carry each milestone's as-built text and Progress line.
The final head's gate run is in the pull request's Validation Evidence.

## The acceptance

- The live check, whole (haiku, the secrets guard loaded from the installed plugins at run time, nothing of it
  committed): the first run ended `live-sheet-check: 51 passed, 1 failed`, the one miss the `two-surfaces` door
  verdict at 1.13 s against a 1 s bound, at load average 62; `--case two-surfaces` alone passed (0.77 s); the
  whole check rerun on an unloaded Mac ended `live-sheet-check: 52 passed`, exit 0. The bound's load sensitivity is
  TECH-DEBT #48. The plan's Concrete Steps said `19 passed` (cases); the check counts checks, 52, and the plan now
  says so.
- C1's evals on the shipped description (`description-v3.md`, word for word in `DESCRIPTION`), run by the
  controller after calibration passed 6 of 6:
  - E1: `v3: PASS  failures 0/30, repurposed 0/10, runs per scenario {'distinct': 10, 'option_gone': 10, 'premise': 10, 'subagent': 10}`
  - E2: `v3: PASS  essential 44/47 (93%), reader no 0, pii and tz passing 30/32 (93%), cap passing 4/15 (26%) (reported)`
  - Subject spend about $18 together (judges not counted), inside the approved budget.
- Tests at the last code change: `sminos/tests/mods/run.sh` 1,043 pass; `tests/mods/run-mods-tests.sh` 247 pass;
  `test_sheet_step` 86, `test_sheet_contract` 40, `test_sheet_log` 42 passed; typecheck clean.

## Rulings received from the composite's writer, and applied

The terminal's row (no head line; the first sentence ending in "?" by one sentence rule with eleven cases; receipts
from the view, else from delivery blocks, drawing only). The surfaces' registration reading (only `*.json`, `mawsd`
first then by name, one trailing slash stripped, the link `url + "/s/" + session`). `model()` projects queued entries
by kind (an M1 defect, fixed in M2's wave). The door refuses a linked or non-regular record or inbox (`bad-record`).
Acceptance 18 reworded (the main conversation's next route, a tool result or a prompt). The waiting notice rides the
idle prompt (my choice, allowed). The idle-flight rule (only a failed idle submit spends the keys that authorized
it). The dismissal receipt. `.incarnation` as the writer's own file in I1. The q1 log dedup as residue. Each is
written into the plan where a later reader needs it, and the composite's sentences they make false are in the
plan's "For the composite's writer", entries 12 to 22.

## Decisions of my own, as controller

- The first receipt is keyed by the start's nonce, not by (seq, source, floor), which mistook a fresh resume for a
  retry; it holds only `{nonce, empty, imported}`, with `before` cut to 200 and a `beforeCount`.
- The rule that converged M6's reviews: a removal or sweep proceeds only on a proven identity (device, inode, and the
  writer's nonce in `.incarnation`), and keeps on any doubt; expiry rechecks the transcript's absence under the lock.
- The floor search prints only `{"floor":n}` (the 4 MiB cut had blocked the import), and the step imports with an
  unknown floor only when `nextId > 1`.
- M7's executor edited `sminos/hooks/CLAUDE.md`, outside M7's Touches, because M6 changed the two hooks it
  describes; accepted.
- M7's task review found only documentation issues; the fix wave was gated and accepted without a re-review.

## Review findings left unresolved (also in the pull request)

- M2 Minor: `RESULT_MAX` assumes at most about 500 withdrawals; a legacy sheet of 1,500 gives a 41,520-character
  result. The wire's cap still holds.
- M4 Minor: the flight transitions could be extracted from `sheet.tsx` (about 1,500 lines). Refactor only.
- M3/M6: a removal that fails during an overlapping `/clear` is left for the sweep.
- M6, ruled residue: a record made again for the same session whose floor cannot be read restarts at q1, and the
  project log's `(kind, src)` dedup then drops the new question's line (and can drop its `answered`). Needs both a
  lost record with a failed floor read, and the same project's log holding that source under the session's writer.
  TECH-DEBT #50.

## Environment

- `ci-gate --gates all` is refused in this repository (no such gate); plain `ci-gate` runs all 24.
- One auto-mode block on a plan commit (classified as information leakage); appealed, granted, re-run.
- The live check's timing bound failed once under heavy machine load; rerun unloaded.

# The branch review's fix wave

The dispatching session's high-rung review of the pull request raised 38 findings. It triaged them into 18 to fix
(R1 to R7 the record, M1 to M6 the delivery, S1 to S5 what a person or another program touches), and the rest were
shipped with or dismissed. The rule: a fault with an ordinary cause (a fork or reload mid-call, a resume during a
retry, a power loss, a failed listing, text a model or a person wrote) is fixed; a fault that needs a file planted
in the person's own sminos home ships as TECH-DEBT.

## How it ran

- Two executors in parallel, each fix written test first: the record and the command (R1 to R7, S3, S4, the plain
  `surfaces` print, the TECH-DEBT rows), and the mod (M1 to M6, the row's and the band's S1, S2, S5). The mod's
  commits were cherry-picked onto the branch.
- A task review, then two re-reviews of the fix ranges. The first found five Important and four Minor items; the
  second found one Important (an interrupted append could delete an accepted answer's image) and two Minor; the
  third was clean.
- Nothing under `sminos/types/sheet/` changed; the generator's digest is still `594200ae…`.

## Beyond the triage

- A `/clear`'s removal also refuses, under the lock, while another live process runs the session. Identity alone
  let a delayed retry remove a record that a resume in another process was using.
- The notification and `show`'s plain print are cleaned like the row. `show` keeps a question's own line breaks,
  each continuation line indented under its first (the dispatching session's ruling).
- Two findings only partly reproduced. In S2 an inherited name (`toString`) leaked but `__proto__` did not. The perl
  half of S5 measured linear and has a timing guard only. The TypeScript trim took 21.9 s on 200,000 spaces before
  the fix.

## Accepted residue

- A same-process `/resume` that lands in the milliseconds between the mod's check and the removal's lock is not
  caught.
- A record whose nonce is damaged is kept until removed by hand. Only a power loss during the mint makes one, and
  the mint is now synced before its link.
- TECH-DEBT rows 51 to 55: the same-user planted-file class (every instance), the floor's twin rules with the perl
  prefilter, and the mod's three shipped items.

## Evidence

- Suites: mods 1,063 pass, 0 fail; `test_sheet_step` 102, `test_sheet_log` 59, `test_sheet_contract` 40 passed;
  typecheck clean.
- The whole live check, on the wave's code: `live-sheet-check: 52 passed`.
- The gates, on the final head: in the pull request's Validation Evidence.
- The executors' full accounts with each RED and GREEN run are in the SDE ledger's task-8a and task-8b reports
  (gitignored, not committed).
