# The ticket board, M1 to M3: execution report (2026-11-27)

The account of running milestones M1 to M3 of [the ticket board spec](2026-11-24-ticket-board-design.md) on branch `ticket-board-spec`, through `doperpowers:subagent-driven-execution`: one executor per milestone (`doperpowers:task-executor`), a task review at each frontier (`doperpowers:task-reviewer`), and the whole-branch review at the high rung the spec names (`doperpowers:reviewer-high`). The spec's Progress, its milestones' *As built* lists, Delegated unknowns and Outcomes & Retrospective carry the result; this file is the record of how it got there. M4 onward write live boards and other repositories and belong to the session that holds the spec.

## Status

Done. Commits `4579bd944..` the branch head: the merge of `origin/main` before M1, then 25 commits. The plugin is `task` 0.1.0 (unreleased until this branch merges). Suite: 235 cases, `bash task/tests/run.sh`, the `task` gate.

## Before M1

- `origin/main` was merged into the branch (`4579bd944`); the branch had been 106 commits behind.
- sminos on `main` was 1.59.0, the spec's facts having been taken on 1.58.0. Everything §10 and D3/D5 rely on was rechecked against the code and, hermetically, the CLI: `who_thread`, `find_target`, `ended_target`, `session_address` and `sminos_threads.py` unchanged since the approval. Two details the first reading had missed were written into the spec: `sminos who` with no session id exits 2 rather than printing nothing, and `who --thread`'s line carries an eleventh key, `not_carried`. For M6 only: the question sheet's work added a second `/clear` witness and a daemon sweep of it, and leaves `cleared_from`, `cleared_witness`, `release_alias` and the guide's use of them as the spec describes.

## Milestones

| Milestone | Built | Review fixes | Review |
|---|---|---|---|
| M1, the ticket verbs | `807c4bb49` | `835c44798`, `00f5d8603`, `1c3dcd267` | clean after three waves |
| M2, the relabel | `7cde22ae8` | `20d03a105`, `fb9d09a6e`, `4e9c827af` | clean after three waves |
| M3, claims | `975c855ea` (with `01bd2ab0f`) | `d99ccc82c`, `3ec169495`, `9a9028b6b` | clean after three waves |
| Whole branch | | `514c65726`, `9a9f7278d`, `b6a6a0288` | clean after two waves |

M2's review and its fixes ran in a separate worktree while M3 was built in the shared checkout; its three fix commits were cherry-picked onto the branch once M3's executor returned (one conflict, in `task/CLAUDE.md`, resolved by keeping both milestones' lines).

## Live cases

Run against two private scratch repositories created for this work, named only through `TASK_LIVE_REPO` and `TASK_LIVE_REPO2`; no real board was written.

- `fork` (21): passed; it now also requires the listed tickets' URLs to be the scratch repository's, against a standing open fixture issue.
- `edge` (the cross-repository unknown): the blocked-by edge between two repositories held.
- `migrate` (22): passed after each M2 fix wave; lint 0 FAIL, a second apply writing nothing.
- `race` (23): run first, as M3 requires: 20 of 20 rounds with one winner, no confirming read missing a lower-numbered claim, `task show` naming each winner. Run again after the review moved the barrier to each claimant's own arrival, and once more after the final fix wave, with the same result.
- `lapse` (24): passed, last at the final fix wave's first commit; its later `task list` runs under a second session id of the driver's, a CLI-level stand-in for another session of the machine.

One race round's ticket was left open with its close comment written; the driver had ignored the close's exit. A failed close exits 1, so the likeliest cause is a refused write after many in a row; the driver now reports a failed close.

## Decisions taken to the design's owner

Each was put to the session that holds the spec and answered; each is written in the spec where it stands.

- An outsider-authored issue with an old status label gets a labels-only relabel row and is never takeable (D6).
- A blocker closed with a null reason counts as completed; only an unrecognized reason fails closed (D1, §5).
- The comments in the board query were measured on the largest board of the cutover and kept (Delegated unknowns).
- `for:` is matched by address; a hand-off before a claim moves it with `task set --to` (D1).
- The organization's repository is described without its contents (D7, O3, M5).

## Verification

- `ci-gate` on the branch: GREEN at `f2d3af7dd`, `4e9c827af` and `9a9028b6b`; RED at `9a9f7278d` on shell-lint alone (an SC2154 in `task/tests/live.sh`), fixed in `b6a6a0288`. The `task` gate alone: GREEN at `1c3dcd267`, `835c44798`, `d99ccc82c` and `3ec169495`. The run at the head is in the pull request.
- `scripts/bump-version.sh --since origin/main` passes with the new plugin at 0.1.0.

## Friction

- The machine ran at a load average between 20 and 200 during the work; the suite took from 80 to 400 seconds, and its timing-sensitive cases were written with wide margins for that.
- `task list --repo` cannot measure a board that has not moved (it refuses a binding other than `task`), so the comments' cost was measured through the same query from a script outside the tree.

## Residue

Listed in the pull request's Residue section.
