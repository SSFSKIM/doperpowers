# Fold summaries: execution report

Spec: `docs/doperpowers/specs/2026-11-12-fold-summaries-design.md`. Branch
`fold-summaries`, executed 2026-11-13 from 4caec06b (the spec's last commit)
by a plan executor running `doperpowers:subagent-driven-execution`: one
`doperpowers:task-executor` per milestone, a `doperpowers:task-reviewer` at
each, and `doperpowers:reviewer-medium` over the whole branch (the rung the
spec's verification entry names). to-human 0.7.4 on `main` becomes 0.8.0.

## Status

DONE. Both milestones are built, every review is clean, CI is green on the
last code commit, and the live check passes every item it automates on that
commit. Pull request: #500 (open, not merged).

## What was built

- **M1, the run tracker and the live line** (2e734e06, review fix 4a590714).
  New `to-human/hooks/mods/folds.tsx` follows the main conversation's kept
  rows (`session.append`, a subagent's ignored), sorts them into runs with
  the view's exported rules (`isRead`, `parse`, `promptRow` on a kept prompt
  whose `task` and `from` it rebuilds, `isApiError`, `keyOf`, `isSpawn`), and
  publishes them in `$.state` under the contract
  `to-human/types/to-human.d.ts`: `folds` (closed runs), `fold` (the open
  run), and `foldLast` (the open run's newest row, which no drawing reads, so
  a result, note or delivery redraws no button). `to-human.tsx` reads the two
  drawn keys where it draws a fold's button (`recordRow` and the mixed
  message's button) and finds the run by the row's place (`labelOf`). The
  live line comes from `lineOf`, the spec's table.
- **M2, summaries** (ca71b3b4, review fix 96afbe02, branch-review fix
  7c47dfd1). A run that closes at a read row once its calls' results are
  kept, and the open run at a turn's end (`turn.complete {turnId: /./}`), is
  summarized by one unawaited `$.model.complete` (`haiku`, or
  `TO_HUMAN_FOLD_MODEL`; effort high; `LABEL_SYSTEM` verbatim) over the run's
  digest. Replies are bound to the session's epoch and the run's generation.
  The tracker's memory is the authority; `$.state` and the session's file
  (`to-human/folds/<session id>.json` in the config dir) are written from it
  through one chain each. A new process publishes its file as closed runs and
  prunes files older than 30 days; a `clear`, `resume` or `fork` resets and
  publishes the new session's file. The gate: a mark seen by the view or kept
  by the tracker, interactive, not MAWS, not `SMNS_INTERNAL`. New live check
  `to-human/tests/mods/live-folds-check.py`. Docs: `to-human/CLAUDE.md`,
  `to-human/hooks/hooks.json`, `docs/whats-inside.md`, `hooks/mods/README.md`.
- **main merged once** (d7ea5c85, PR #499). Conflicts: the version (0.8.0
  kept) and `to-human-native.test.ts`'s list of non-drawing hooks. Seven of
  #499's new "rows nothing keeps" tests found a run's button by
  `working record` where the run holds a call; they now find it by the call's
  line. Each was checked first: the tracker and #499's view agree on every
  run's bounds in all seven.

## Reviews and what became of their findings

| Review | Range | Findings | Outcome |
|---|---|---|---|
| M1 task review | 4caec06b..2e734e06 | none blocking; Minor: validation output noisy | approved |
| authoring session | — | the open run's newest row under a key of its own | fixed 4a590714, re-reviewed clean |
| M2 task review | dbfb9284..ca71b3b4 | Important: the reset read a session's file ahead of its pending write (reproduced); Minor: the digest cap excluded separators | fixed 96afbe02, re-reviewed clean |
| authoring session | — | the summary gate also opens on a kept mark (a skipped run settles for good) | fixed 96afbe02 |
| branch review, `reviewer-medium` | 48e1a9a9..83473620 | P2: a late result on a closed run left it not live, so its summary stayed stale (reproduced) | fixed 7c47dfd1, re-reviewed "correct" |

The recurring Minor, "validation output not pristine", is environmental and
dismissed: the two local doperpowers typecheck errors (`appeal.tsx:409`,
`fork-guard.test.ts:143`) come from the worktree's copied MCP type roots,
which predate `mcp__doperpowers__appeal` (CI's `mods-types`, which lays fresh
roots, passes), and the LICENSE/icon notices of `claude plugin validate` are
the plugin's standing directory-submission warnings.

## Evidence

- `to-human/tests/mods/run.sh` on 7c47dfd1: 272 pass, 0 fail;
  `session-places: 13 searches as expected` (baseline 158).
- `claude plugin validate to-human`: passed; declares and writes
  `to-human.folds`, `to-human.fold`, `to-human.foldLast`.
- `tests/mods/typecheck.sh`: to-human, sminos, devcloud, web clean.
- `ci-gate` GREEN, 20 of 20: 4a590714 (run 43349356580), d7ea5c85
  (43352064610), 96afbe02 (43361450869), 7c47dfd1 (43365315974). ca71b3b4 was
  RED 1/20 on one `sminos-suites` daemon-log assertion this branch does not
  touch; re-run green on 3a20532c.
- `live-folds-check.py` on 83473620 (the code of 96afbe02; the later fix is a
  path the live run does not reach), Claude Code 2.1.323, haiku through the
  gateway: PASS 1, 2, 3, 4a, 4b, 5, 6, 7. Log
  `~/.local/share/fold-runs/final-live-folds-83473620.log`; M2's own run and
  frames are `m2-live-folds-2.log` and `evidence/m2-live-folds-2-*-frames.txt`
  beside it. Item 5's press is pinned by the kit, not live (the tmux main
  screen takes no click).
- Acceptance 1 was also seen live after M1
  (`evidence/m1-live-line-frames.txt`).

## Decisions made during execution

All are in the spec's Decision Log, dated: M1's eight (the take-up, the reset
and the lazy start-up read built in M1; `task` rebuilt only from a leading
`<task-notification>`; the extra exports), the `foldLast` split, M2's twelve
(a turn's end as a step; a skipped run settles; a result bumps the
generation; what the file stores; "a new process"; the reset's file; no
config dir, no file; the matcher; the live checks listed in
`to-human/CLAUDE.md` because `tests/CLAUDE.md` lists none; the digest's
markers; the live check's reach), M2's review round, and the branch review's
fix.

## Surprises

In the spec's Surprises & Discoveries: the loader takes `$` only into
top-level functions and `$.env.get` only with a literal name; the kit's own
`$` has no `state`; `isMeta` tallies over the owner's transcripts; the
transcript file keeps a mid-turn delivery as a `queued_command` attachment;
the summary's timing live (1 to 3 s after the turn's end).

## Friction routed around

- The worktree isolation guard refused several plain commands as git
  operations "too complex to verify" (a `cp` from the main checkout's path, a
  `ls` with a brace expansion, a `git rev-parse` inside a comparison); split
  commands went through. The task reviewer updated the existing tracker entry
  (`doperpowers/live/worktree-guard-refuses-commands-that-run-no-git.md`).
- The worktree had no engine type roots (gitignored); copied from the main
  checkout. Their MCP roots are stale, hence the two local typecheck errors.

## Residue

- **A fork starts with no summaries.** A `fork`'s new session id has no file,
  so the folds of the conversation it forked from read `working record` in
  the fork. Copying the parent session's file at a fork would close it, if
  the fork's `classic.SessionStart` can name the parent; the authoring session is telling the human it is a known
  limit.
- **Spawns are not remembered across a reload.** After a reload the
  tracker's remembered spawns start empty, so a pre-reload spawn's failure
  notification is a delivery to the tracker while the view shows it: one fold
  boundary differs, rarely. Publishing the spawn ids in `$.state` would close
  it.
- **Unconfirmed: whether #499 explains the original report** (one run drawn
  as many folds). The spec's Surprises records the reproduced cause and what
  it does not explain; `/to-human-dump` (#499) gives a way to capture the
  view's state the next time it is seen.
