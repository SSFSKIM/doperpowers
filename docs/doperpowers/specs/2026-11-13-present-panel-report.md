# The panel: execution report

The execution of [the spec](2026-11-13-present-panel-design.md) (M1 to M3) on branch `present-panel`, from 53c84adb (the spec as reviewed) to the head the pull request names. The spec carries the design, every decision taken during execution (its Decision Log), what was found (its Surprises & Discoveries) and the retrospective. This report is the account of the run: what was dispatched, what each review found, what was verified and with what, and what is left.

## How it ran

The work used subagent-driven execution, with a fresh `doperpowers:task-executor` (opus, high) for each milestone and a `doperpowers:task-reviewer` (sol, xhigh) at each frontier. Findings went back to the executor that wrote the code. The whole-branch review was `doperpowers:reviewer-high`, as the spec's Decision Log names, and a fresh fixer took its findings. Every model run beyond the haiku live check was cleared with the designing session before it launched.

| Milestone | Commits | Task review |
|---|---|---|
| M1, the panel server and the base | ebc15016, a6549d08; fixes bdd8e9f6, 67871650, 47bce689 | clean after three fix rounds (R1 to R7) |
| M2, the tool and the fork | 7b75c023, fe908ee3, 4f9edcb1; fixes a4e6b5f7, 7f919c35, 3fb7bda0, 44e1b592, 3670dfe0 | clean after three fix waves |
| M3, the rule, its evaluation, the documents | 392d9a2f, 7591a94a, 470eee26, a6096d6e, 7e287d8c, 13ffae25, 360860e1 | clean after one fix wave and three minors |
| Branch review fixes | 68e35c89, 070921a9, ea7303d3 | `reviewer-high`: "incorrect" (five P2s), then one more P2, then "correct" |

## What each review found, and what became of it

**M1.**
- R1: a failed `tailscale serve status` lookup was read as "no mapping", so the server could replace someone else's mapping. A failed lookup is now unknown, and nothing is configured.
- R2: a tag left open at the draft's end escaped publishing's cut. Every open tag is now cut.
- R3: a cold-start `OSError` printed a traceback. It is now one line on stderr.
- R4: the spec described `seenAtOpen` wrongly. The spec was corrected.
- R5 to R7: inserting the server's script at the first textual `</head>` could land inside a comment. A guard string tried first broke valid comments. A fallback tried next could mark an unseen publication as seen and bring checked notes back. The script is now appended at the page's end (spec c40d084e).

**M2, first review.**
- The guard failed open after a reload, for a closed run's fork and for a failed restore.
- A plugin's internal tool call consumed the session's notice.
- A completion during the BUSY check dereferenced a cleared run.
- A reload after a committed publish reported FAILED. This one needed a design fix: the run's `phase` and `startedAt`.
- The test harness's catch re-ran everything downstream, which hid the BUSY failure.

**M2, second review.**
- An unlisted former fork passed while the ids were unread, and the 200-id cap could evict one.
- A queued write could store a stale snapshot over a restored record.
- A publish could go ahead when its `publishing` phase had not been kept.

**M2, third wave.** One note per change, after the owner-model runs showed a note per place. The review was clean.

**M3.**
- The eval report called its rebuilt requests exact, but nine turns had substituted messages.
- Resume skipped the missing repetitions of a partly finished turn.
- The spent-plan stop was checked between repetitions only.
- Then three minors: one contaminated run missed, the stop not checked before a retry, and stale wording.
All are fixed. The rebuild is now byte-exact, and the five turns whose content had differed were re-run. No count moved.

**Branch review.**
- An old panel fork could write the next run's draft.
- Two servers on different ports could run over one panels directory.
- A version replacement could cut a publish, leaving a new page with `written` unset.
- Two harness findings, the same as M3's.
- Then: a fork restored in its `publishing` phase could still write the draft.
All are fixed. The last round's verdict was "correct".

## Verification

The commands are the spec's Concrete Steps. Each result below is from the run that reported it, and the last run of each is on the final code.

- **Panel server suite:** `python3 -W error::ResourceWarning -m unittest discover -s to-human/tests/panel` gives `Ran 73 tests … OK` (the final-fix report, on 070921a9; ea7303d3 touched no server file).
- **Base, in a browser:** `bash to-human/tests/panel/live-base-check.sh` passes every check on 070921a9. The checks cover placement at 1280 and 600 wide, the count, a check surviving a reload and another browser, one reload per publication keeping the scroll, a look reported only from a visible tab, Korean, a hostile draft running no script and loading nothing from another host, a head comment holding `</head>`, and one note with several marks.
- **Kit tests:** `bash to-human/tests/mods/run.sh` gives 374 pass, 0 fail on ea7303d3.
- **Eval logic:** `python3 tests/output-styles/test-present-eval.py` gives 17 of 17 on 360860e1.
- **Versions:** `scripts/bump-version.sh --since origin/main` reports to-human 0.8.2 to 0.11.0 and doperpowers 7.220.0 to 7.222.0.
- **CI:** `ci-gate` is GREEN on ea7303d3, 20 gates (https://github.com/SSFSKIM/doperpowers/actions/runs/43584543954). On 931ae2dd, the head the pull request opened at: GREEN, 20 of 20 (https://github.com/SSFSKIM/doperpowers/actions/runs/43586228608).
- **Acceptance 1 to 10 and 14, live:** `python3 to-human/tests/mods/live-present-check.py` on haiku (M2) and on fable (M3's re-run: `main`, `unseen`, `guard` in five modes, one of them Korean, and `plan`), every item passing on fable. Acceptance 3, 4, 5 and 8 are judged on fable, by the designing session's ruling, with haiku recorded as the version's limit.
- **Acceptance 11:** the server suite's refusal tests and the browser check.
- **Acceptance 12 and 13, live:** run on devcloud host `dc-c53-g1a-980a` in M1 and again in M3. A panel written on the host opens in the MacBook's browser, and a check made there reaches the host's `state.json`. From the tagged host, every probe of the Mac's panel is 403 with no body: the honest Host, the local Host, a forged login, and a made-up token. Every `tailscale serve` mapping made was removed on both machines.
- **Acceptance 15:** the replay in `tests/output-styles/to-human-present-eval.py`, reported in [the eval report](2026-11-13-present-panel-eval.md). It is met for designs (9 of 9), for a decision the dialog cannot carry (2 of 3) and on the text side (0 of 36). It is not met for revisions (0 of 9).

## Model runs

All of these were cleared with the designing session before they launched.
- **M2:** the haiku live check, and the fork check on opus and fable (one run each, then five more each with the parent mid-task).
- **M3:** the replay on each turn's own model and effort. The first round was 81 runs and 13 diagnostics. The counted rounds were the control (20 runs), the rule's first wording (60), its second wording (60), and the five re-run turns (15). The fable acceptance re-run was 8 live runs.
- **Cost and interruptions:** the measured cost is in the eval report's cost sections. One spent fable plan paused the work at 08:30Z, and the harness now stops on one and never retries a 429.

## Environment friction routed around

- The worktree isolation refuses compound shell commands that name git, or whose shape it cannot verify (dozens of refusals across the agents). Its tally is in the friction tracker (`worktree-isolation-refuses-bash-commands.md`, `worktree-guard-refuses-commands-that-run-no-git.md`).
- A plugin's `$.agent.spawn` waits on a permission dialog in `auto` mode. It was logged by the M2 executor (`mod-agent-spawn-waits-on-a-permission-dialog.md`) and resolved in the code.
- `devcloud vm ssh` runs zsh, which does not word-split `$var`. The existing tracker entry was updated.
- The prototype's static server holds port 4777 on this Mac. While it runs, panels at the default port fail here; it is the designing session's to stop after the merge. Every check used its own `PANEL_PORT`.
- The gateway's account ran out of fable plan usage at 08:30Z, and a second account served fable from 08:31Z.

## Left behind

In the pull request ([#503](https://github.com/SSFSKIM/doperpowers/pull/503)):
- **Residue**: the rule's miss on revisions (the prompt-time note ticket); an old server serving a deleted base until a session starts; no guard while to-human's own module reloads; the panel in MAWS.
- **Unresolved Review Findings**: five minors, each with where it is and why it was left.

The branch is not merged. After the merge, the designing session edits the owner's `~/.claude/CLAUDE.md` (the rule line) and `~/.claude/settings.json` (`PANEL_REACH`), and stops the prototype's server on port 4777.
