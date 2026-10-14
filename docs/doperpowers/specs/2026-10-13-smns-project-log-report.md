# `.smns` project log: execution report

This report covers the execution of
`docs/doperpowers/specs/2026-10-13-smns-project-log-design.md`. The work
ran on branch `smns-project-log` from main 0f98dfc8, with origin/main
(7.152.1) merged in at c98ba037. A plan-executor ran it as
subagent-driven execution: a fresh opus task-executor built each
milestone, and a sol/xhigh task-reviewer checked it at each frontier.
The spec is the primary record. Its Decision Log carries every decision
and ruling made during execution, its Surprises & Discoveries every
measured fact, and its Outcomes & Retrospective the summary. This file
gives what each milestone delivered, the evidence, and what is left
behind.

## Baseline (before M1)

| check | result |
| --- | --- |
| `tests/sminos/run-sminos-tests.sh` | all 860 assertions passed |
| `tests/issue-tracker/test-execute-dispatch.sh` | all tests passed |
| `tests/issue-tracker/test-review-dispatch.sh` | all tests passed |
| `scripts/lint-shell.sh` | clean |

## Milestones

| milestone | code commits | review | suite after |
| --- | --- | --- | --- |
| M1: project identity and the log | 7f3f8b9f, d08376c1, eb6a5ede | clean after 2 fix waves | 1004 |
| M2: the project family | 5dd82ba4, 89282adb, faa23f6c, 48721e99, 0ed8f8fb | clean after 2 fix waves and 2 rulings | 1118 |
| M3: messages to the host and the in-charge line | 09775a35, 7788bd13, 91b7cfa6, 8136a2e8, 2fc95340 | clean after 3 fix waves and 2 rulings | 1308 |
| M4: the mirror and the daemon | e4204b38, db31a289, da97a875, e7e55aef | clean after 1 fix wave and 1 ruling | 1439 |
| M5: the skill and the preamble, as behavior | 7009154f, 619308dc | clean after 1 fix wave | 1453 |
| M6: docs, acceptance, version | c98ba037 (merge), 81e0c265, 55491f63, 38e94907, 9b8fc8b2 | clean, plus one minor test fix | 1485 |

- **M1** added `.smns` and `project init|show|attach`, and `resolve_project`
  with its three outcomes. Each writer appends to its own file, with `seq`
  assigned under flock and the shared `.sync.lock`, and `ts` carries
  milliseconds. Display merges writers by `(ts, writer)` and keeps each
  writer in `seq` order. Cursors are merged under a lock. Delivery records
  hold a settled prefix plus one pending event, and `deliver_next` is the
  one delivery operation. `send` also goes through it, so a crash between
  append and push is recovered. Tags take four forms; ambiguous, unknown,
  and mixed-project tags are refused. Batch dedupe is by `(kind, src)`.
  `migrate` imports the old chats.
- **M2** derives membership from `joined`/`retired` and reconciles on
  sight. A closed seat-less session is retired as `ended`; a session joins
  only when its kind is interactive or bg and its entrypoint is not `sdk`.
  `list`, the chart, and the TUI are flat per project, with the columns of
  §7. CLI targets resolve the way tags do. `spawn`, `fill`, `resume`,
  `retire`, `status`, and `seat add` record their lifecycle. The family
  reach (`--group`, `--parent`, `--team`, `--cascade`) is gone. The
  dispatch scripts pass `--brief`, with contract tests through the real CLI.
- **M3** added `hooks/smns-record.sh` on `Stop` and `SessionStart`, and
  `sminos record`. Export is by position, idempotent by `(kind, src)`. The
  mark grammar is ported in `sminos_marks.py`, parity-checked against the
  mod's 47 fixtures. Async asks become `question`/`answered` events, and
  `chat --host` shows them. `charge` and `derive` work, with the fork's id
  pinned and its transcript deleted. The hook is bounded: lock waits have
  deadlines, and no alarm runs over a migration step.
- **M4** added `sminos_daemon.py`, with `daemon run|tick|install|status`,
  the sync invariant, and the machine claim under `$SMINOS_HOME/daemon/`.
  `state` publishing is two-tick, keeps the candidate word, and runs for
  remote projects only; `renamed` is published everywhere. One
  cross-process derivation runs at a time. A say to a remote member nudges
  the daemon. `install` writes a launchd plist pointed at the marketplace
  clone and never loads it, and `run` restarts when the code changes.
- **M5** rewrote SKILL.md and the 39-line spawn preamble, under
  writing-skills with a before/after eval. Transcripts are in
  `docs/doperpowers/specs/2026-10-13-smns-project-log-m5-evals.md`; the
  verdicts are in the spec's Surprises.
- **M6** merged main, cleaned up the preamble renderer, and added the
  CLAUDE.md repo-map lines and the 2026-09-26 spec's Decision Log line. It
  ran the live acceptance and fixed the three defects it found (F1–F3,
  below). Version is 7.153.0.

### M5 eval verdicts

| scenario | old text | final text |
| --- | --- | --- |
| (a) `@all` for a blocking change | 2/2 | 2/2 |
| (a2) routine news, untagged | 0/3 | 3/3 |
| (b) the human through `<message>` | 2/2 | 2/2 |
| (c) a sibling for standing work, no session for bounded work | 0/2 | 2/2 |
| (d) a board worker escalates by parking | 1/2 | 3/3 |

## Acceptance

The full transcript, with commands, output, and a verdict per step, is
`docs/doperpowers/specs/2026-10-13-smns-project-log-acceptance.md`.

Steps 1–5 ran live: real interactive Claude Code sessions (harness
2.1.299) driven through tmux, with this branch loaded via `--plugin-dir`
and the installed doperpowers plugin disabled for those launches only.
Each session ran under a temporary `SMINOS_HOME` and ran its own sminos
commands. Step 6 ran on the stub harness, because a temporary HOME
cannot authenticate a real `claude`. The two-home `daemon run --interval
1` delivered 40 timed messages, the slowest in 1.53 s, each exactly
once. Step 7 is the suites below.

| step | verdict |
| --- | --- |
| 1. `list` shows both sessions | pass |
| 2. untagged is recorded, `@b` delivers, `@all` wakes | pass |
| 3. `<message>` and the async ask in `chat --host` | pass (F1 found) |
| 4. spawn provenance, retire the spawner, ambiguous `@c` | pass (F2 and F3 found) |
| 5. `charge` and `derive` | pass |
| 6. two homes, the mirror, the daemon | pass (stub) |
| 7. the suites | pass |

The live run found three defects. All are fixed in 38e94907 and pinned
by tests:

- **F1:** a Stop hook can run before the harness flushes the turn's last
  record (the flush runs every 100 ms, and none runs before Stop hooks).
  One mark in 24 was exported a turn late. `record` now polls for the
  payload's `last_assistant_message`, within its budget.
- **F2:** a retire of a human-opened session was undone by reconciliation
  2 s later. A retirement now holds for the life of the process it saw.
- **F3:** a `claude --bg` seat did not inherit `SMINOS_HOME`. Seats now
  launch with a settings overlay that carries it.

The F1–F3 fixes are covered by regression tests. They have not been
re-run live.

## Final verification (controller, at 520f2d1e)

    tests/sminos/run-sminos-tests.sh               all 1485 assertions passed
    tests/issue-tracker/test-execute-dispatch.sh   all tests passed
    tests/issue-tracker/test-review-dispatch.sh    all tests passed
    tests/mods/run-mods-tests.sh                   all checks passed
    scripts/lint-shell.sh <the 5 changed shell files>   Linting 5 shell files, rc 0
    git show --cc c98ba037                          empty (the merge was conflict-free)
    version fields (4 manifests)                    7.153.0

`shellcheck -S warning` flags `CLAIM_LANES` (SC2034) in both dispatch
scripts. That line predates this branch.

## Environmental friction and incidents

- **The real registry was migrated once.** In M1, an executor ran
  `sminos.py project show` without `SMINOS_HOME`. The automatic `migrate`
  imported the operator's two real family chats under `~/.claude/sminos`.
  The executor's attempt to restore them was refused by the permission
  classifier, and it was not worked around. The incident was escalated,
  and the human approved the restore, which the authoring session ran on
  2026-10-14. Every later dispatch carried an isolation line. F3 closed
  the same failure at the spawn boundary.
- **The worktree guard refuses some Bash.** It refused commands in which
  `git` or a `HOME` override appears inside a heredoc or a compound
  construct. Commands were split into plain ones, and reviewers relied on
  the suites, which set their own homes.
- **Probes of the real harness (2.1.299) cost a few small model calls in
  /tmp**, all cleaned up afterwards. They established three facts: `-p`
  runs register as `interactive` with entrypoint `sdk-cli`; `--session-id`
  pins a `--fork-session`; and `--tools` swallows a prompt that follows it
  directly.
- **The live acceptance left one trust entry.** It added an entry for
  `/private/tmp/smns-acc/R` to `~/.claude.json`. It was left in place to
  avoid racing the harness's writes, and the human can remove it.

## Left behind

- **The async questions of a MAWS session.** Under `MAWS_NATIVE_TO_HUMAN`,
  asks go through `mcp__maws__ask` and never become `question` events.
  MAWS sessions are the ones most affected. This is recorded in §9.
- **A seat whose cwd moved after it joined is listed twice** when `list`
  runs from a directory in no project, once under each project. This is a
  deferred minor review finding.
- **Seats spawned before F3** carry no `SMINOS_HOME` in their settings,
  and a resume cannot add it.
- **The F1–F3 fixes have not had a second live pass.**
