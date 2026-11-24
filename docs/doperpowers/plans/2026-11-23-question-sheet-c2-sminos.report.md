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
