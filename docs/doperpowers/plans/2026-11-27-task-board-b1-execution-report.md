# Task Board, B1 M1 — execution report (2026-11-28)

> **Executes:** `docs/doperpowers/plans/2026-11-27-task-board-b1.md`, milestone M1 only (gate G1), built from the text at `5d509ad59`. **Composite:** `docs/doperpowers/specs/2026-11-27-task-board-design.md`, child B1. **Branch:** `task-board-spec`, whose pull request carries both documents and M1.

## How it ran

The work ran through `doperpowers:subagent-driven-execution`:
- One `doperpowers:task-executor` built M1, and the same executor was resumed for every fix round.
- One `doperpowers:task-reviewer` reviewed it at the dependency frontier.
- The whole-branch review ran through `doperpowers:review-code` at the medium rung that the document's Verification names.

The pre-flight found the plan sound, and `origin/main` (`40b79a7d1`) was already the branch's base, so the merge was a no-op. The one change it made was a line in "How it lands": M1 lands on the spec's own branch, by the dispatching session's ruling.

| step | range | result |
|---|---|---|
| pre-flight | `5d509ad59..4e527dec3` | "How it lands" names the branch |
| M1 built | `4e527dec3..601ffa971` | gate GREEN |
| task review, round 1 | 6 Important, 2 Minor, plus the coordinator's refused-then-reopened test | fixed in `ae692122e`, gate GREEN |
| task review, round 2 | 2 Important (introduced by round 1), 1 Minor | fixed in `5b773a653`, gate GREEN; review clean |
| spec write-back | `fb92b3816`, `ab1c32252` | as-built interfaces, Progress ticked, the composite writer's list |
| whole-branch review, round 1 | 1 P1, 6 P2 | fixed in `3433398f7` (code) and `cf7870475` (document), gate GREEN |
| whole-branch review, round 2 | 2 P2, 1 P3 (document) | fixed in `5cba68a99` (document) and `9cd7e1354` (code), gate GREEN |
| whole-branch review, round 3 | verdict correct; 1 P3, left as is (below) | converged |

M1's gate line is `ci-gate --gates sminos,sminos-suites-a,sminos-suites-b,sminos-suites-c,shell-lint,version-bump`. It was GREEN on `601ffa971`, `ae692122e`, `5b773a653`, `3433398f7` and `9cd7e1354`. Every commit after `9cd7e1354` touches only the two documents and this report.

## Decisions the dispatching session confirmed

Each of these was checked by the dispatching session against the design.
- **Ten readings of gaps.** These are the README's "Readings fixed with the set", and the session kept them.
- **Every first verdict is kept by its key, refusals included.** Re-judging a refused line was tried and dropped. A keyed comment refused `closed` applied after a reopen, and a `done` on an id not yet made would apply once that id was made. §3 now says that a retry after a refusal needs a new key.
- **One limit of the /clear pair is accepted.** When both of its writers fail, each past its 10 s wait, the alias is released anyway. It goes to D5 through the B1 document's list for the composite's writer.

## Decisions made in execution

These are recorded in the B1 document's "As built" paragraph under M1:
- The record hook's pair write pauses its alarm and moves its wall-clock deadline by the same time.
- The start hook's timeout is 30 s.
- The bind runs after the record hook's join.
- A pair is replaced when a reopened session is cleared again.
- The door's memo is reset when the pairs change, and a `shown` uses no memo.
- A door line where no store exists makes the store.
- The door's wire rules beyond the schema are published with rejection vectors.

## Left for later

- **`shown --keys` resolves the target once per outcome** under the store's lock (whole-branch review, round 3, P3). This costs one membership scan per waiting outcome at a start. Most starts mark a few keys, so it was left as is. A memo scoped to that one step would restore a single scan.
- **The illustrative history in `examples/state.json`** counts sequence slots only for the outcome and the final `shown` step (task review, round 3, Minor). It does not change how a snapshot is read, and it matters only if the example is replayed as a history.
- **Unguarded `daemon_log` in `release_alias`.** The release's own failure handler in `sminos.py` calls `daemon_log` unguarded. That predates this branch and is outside the task path, which M1 made best-effort.
- **Notes for M2.** M2 replaces `told_of` with §3's table and writes `send: due`, and its hourly duty also prunes the kept keys of unknown ids.

## M3 — the `task` verbs (2026-11-28)

Built on `task-board-b1-m3` from `main` at `f695ab504`, once the `task` plugin's change to `create` and `claim` (#648) had merged; one PR. One `doperpowers:task-executor` built it and was resumed for the fix. The milestone's review was `doperpowers:review-code` at the medium rung the document names; the dispatching session ruled that, for a PR of one milestone, it stands in for a separate task review of the same range.

| step | range | result |
|---|---|---|
| M3 built | `f695ab504..5db5b5bc6` | `ci-gate --gates task,version-bump` GREEN |
| review, medium | 2 P2 | one fixed in `0c0844640` (gate GREEN), one recorded |
| main merged in | `497d8d875` | the doperpowers bump on main had moved past the base |

Decisions made in execution are in the document's "As built" paragraph under M3. Recorded, not fixed: the ticket-number refusal of `revise`, `withdraw` and `reopen` reads only the first argument, so `task revise --title X 7` reaches sminos and exits 1 or 3, not 2. The plain form the document names exits 2, and sminos refuses the others. Found for another writer: the ticket board's spec still says the human's verb names stay unused (the document's list for the composite's writer).
