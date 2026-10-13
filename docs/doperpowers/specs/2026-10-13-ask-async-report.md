# AskUserQuestion with `async`: execution report

Spec: `docs/doperpowers/specs/2026-10-13-ask-async-design.md`. Branch `ask-async`, cut from main at `9ce2f2cd`.

Executed 2026-10-13 by the plan-executor as the subagent-driven-execution controller. Each milestone was built by a fresh `doperpowers:task-executor` (opus/high) and reviewed at its frontier by `doperpowers:task-reviewer` (sol/xhigh). The whole branch was then reviewed by `doperpowers:reviewer-high`, as the spec's Decision Log names.

## Status

DONE. All three milestones are reviewed clean, and the whole-branch review returned "correct" after two fix rounds. Every acceptance item, 1 through 13, passed live on the finished branch.

## Commit range

`9ce2f2cd..HEAD` (23 commits before this report). Grouped by milestone:

- **Pre-flight and spec folds:** `6c946cc3`, `138b750b`, `c713c265`, `95e95eda`, `d31a773f`, `b604ec9d`, `1f4f65c2`, `38078643`, `7ff92654`, `53d0cd77`, `28c85d7c`, `909e0836`.
- **M1, the tool and blocking parity:**
  - `802f10bf`
  - review fixes `9abc85ee` and `4ab20a04`
- **M2, asking without waiting:**
  - `8ddc8c11`
  - review fixes `e6927ce5` and `11a50ecf`
- **M3, `<need-input>` retired, the style, evals, acceptance, version 7.148.0:** `9ab51c01`, `50779a81`, `d77bf76c`.
- **Branch-review fixes:** `0fac4480`, `1794a19f`.

## Tests

Run at the final HEAD in this session:

| Check | Result |
|---|---|
| `tests/mods/run-mods-tests.sh` | `167 pass`, `0 fail`, then `ask search: all checks passed` |
| `tests/claude-code/test-to-human-stream-hook.sh` | `to-human-stream hook: all checks passed` |
| `npx -p typescript@5 tsc -p hooks/mods/tsconfig.json` | exit 0 |
| `claude plugin validate .claude-plugin/plugin.json` | `✔ Validation passed with warnings` |

The validate warnings are the baseline main already has. M1 compared them against a detached worktree of main: two frontmatter warnings, plus gating-hook notes from the other mods, which drop from 9 to 8 because to-human's `prompt.submit` hook is gone.

## Live acceptance

The executors ran these checks in tmux sessions with `--plugin-dir` set to the worktree. Their evidence lines are in the gitignored per-milestone reports under `.doperpowers/sde/2026-10-13-ask-async-design/`.

| # | Result | Evidence |
|---|---|---|
| 1 | Pass | The recorded `tool_result` contents of the branch's tool and the built-in compared byte-identical (`IDENTICAL`). |
| 2 | Pass | The answer was delivered mid-turn as a `hook_additional_context` attachment. |
| 3 | Pass | The answer was delivered as a plugin prompt while the session was idle. |
| 4 | Pass | Esc kept the ask open. |
| 4a | Pass | Two asks, each delivered exactly once. |
| 4b | Pass | After an interrupt, the held answer rode with the human's next prompt. |
| 5 | Pass | The built-in was withdrawn and refused, including while an async dialog with the same question was open. |
| 6 | Pass | A subagent's call was refused. |
| 7 | Pass | Resume rebuilt open and answered asks, and no ask from a refused call. |
| 8 | Pass | An old `<need-input>` draws as a message. |
| 9 | Pass | A blocking Esc ends the turn: the queued Write was not run and no `x.txt` was written. "Chat about this" continues the turn. |
| 10 | Pass | The hooks module loaded with no refusal. |
| 11 | Pass | The eval met its bar on round 2 (below). |
| 12 | Pass | A blocking paste reached the model as an image block. |
| 13 | Pass | An async paste arrived as a path line, and the model Read it. |

## Eval

The eval compared main (before) with the branch (after): `claude-opus-5-5`, the to-human style, three runs per scenario.

| Scenario | Before (main) | After (branch, round 2) |
|---|---|---|
| S1: independent work plus a needed preference | 1/3 `<need-input>` mark. In the other 2, the model referred to a question it never wrote. | 3/3 async ask, with `todo.py` written in the same turn |
| S2: a decision everything depends on | 3/3 built-in, blocking | 3/3 new tool, blocking |
| S3: no question warranted | 3/3 no ask, task done | 3/3 no ask, task done |
| Marks / built-in calls | 1 / 3 | 0 / 0 |

Round 1 used the spec's one-line style summary and missed twice: S2-3 asked async and then waited, and S1-3 recommended instead of asking. Round 2 revised only the style paragraph and restored the old style's guard sentence. The style was confirmed active in all 27 eval transcripts. The transcripts, driver and scorer are in `.doperpowers/sde/2026-10-13-ask-async-design/m3-eval/`.

## Design-session changes absorbed

- **Images came into scope mid-build.** In a blocking ask, kept pastes go to the model as image blocks. In an async delivery and in "Chat about this", they go as `[Image source: <path>]` lines. That is the engine's own source-only form, not the `[Image: source: …]` form the brief gave, which the engine uses only beside dimensions.
- **Turn end.** The design session first preferred ending the turn without `$.turn.abort`. A probe showed the abort spares running shells and Monitors, while the no-abort variant runs Stop hooks. With the design session's agreement, the turn still ends with `$.turn.abort` plus an empty step.
- **Accepted deviations.** These were confirmed by the design session:
  - A refusal reaches the model wrapped in `<tool_use_error>`.
  - The tool's description is captured from the built-in's `tool.describe`, because `$.tool.list()` truncates at 300 characters.
  - Another plugin's `$.ui.ask` passes the withdrawal hook.
  - The literal-`(Image attached)` case is a known limit.

## Review history

- **M1:**
  - **Finding:** removed pastes were sent. **Fix:** a kept-paste count rule.
  - **Finding:** images were dropped on "Chat about this". **Fix:** path lines.
  - **Finding:** new validate warnings. **Fix:** `.catch` policies.
  - **Finding (re-review):** a literal-marker case. **Disposition:** recorded as a known limit.
- **M2:**
  - **Finding:** a rejected prompt pass lost its answers. **Fix:** the answers are put back.
  - **Finding:** a human row was read as a delivery. **Fix:** only framed rows count.
  - **Finding:** a truncated grep fallback rebuilt silently. **Fix:** narrowed patterns, exit-status handling, and a diagnostic.
  - **Finding (re-review):** mixed-context deliveries were missed. **Fix:** fixed, with a real-grep shell check.
- **M3:** clean. The two minors were deferred.
- **Branch review (reviewer-high):**
  - **Finding:** resume ignored rewind ancestry, and multi-line Chat answers lost their image mark. **Fix:** both fixed.
  - **Finding (re-review):** the ancestry fix had dropped same-response sibling results. **Fix:** fixed by gating ancestry on a rewind record and mirroring the engine's `i1r` recovery. Final verdict: correct.

## Environment notes

- **Function hooks forced on.** User settings force function hooks on, so the built-in baselines ran with the installed 7.147.1 plugin's mods loaded. That copy has no ask mod and no `turn.step` hook.
- **Plugin precedence.** `--plugin-dir` overrode the installed copy; the debug log reads `Plugin "doperpowers" from --plugin-dir overrides installed version`.
- **Scripted session pitfalls:**
  - A fresh git directory's trust dialog puts "No, exit" first, so a script must press Down before Enter.
  - Prompts passed through tmux need single quotes.
- **Clipboard.** The human's clipboard was saved and restored around every image paste.

## Unresolved review findings (deferred)

- **`hooks/mods/ask.tsx` is about 1,250 lines.** Its pure helpers could move to a sibling `.ts` file that `ask.tsx` re-exports. The spec's Interfaces place the exports in `ask.tsx`.
- **The resume grep fallback for transcripts over 4 MiB has limits:**
  - a 4 MiB ceiling on its filtered output, logged when hit;
  - no ancestry;
  - no live test.
- **The eval scorer does not enforce S1's same-turn requirement.** The recorded runs were checked by hand.
- **A removed paste can still be sent** when the human ends their own answer with the literal `(Image attached)`. This is a known limit.

## Residue

- Withhold `mcp__doperpowers__AskUserQuestion` in `~/.claude/agents/astra.md` and `sol-xhigh.md`. These are user config, which the design session will update after merge.
- MAWS must learn the tool:
  - It draws the report itself under `MAWS_NATIVE_TO_HUMAN`.
  - A plugin tool's `tool_use` row is written to the transcript only after the call resolves, so a transcript watcher cannot see an open blocking ask.
- The smns project-log spec's `need-input` event source is now an async ask. The design session relays this to that spec's owner.
- An in-session rewind leaves the abandoned branch's asks in view until resume, because no hook-visible rewind event exists. This needs an engine event or a cheap signal.
