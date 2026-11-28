# Task Board B5: the ledger

> Child B5 of `docs/doperpowers/specs/2026-11-27-task-board-design.md` (parent pin `a99ce15dd`). This file holds what B5's brief asks of its ledger: the thresholds, set before the first run; every run's raw rates; the rates of the behaviours that are measured with no threshold. The words the runs settle are in `2026-11-27-task-board-b5-words.md` beside it.

## What is run

The question sheet's eval harness (`tests/output-styles/question_sheet.py`, unchanged) continues a scripted Claude Code session live, in the simulated project `tally`. B5 adds, beside it:

- `tests/output-styles/task_board.py`: the board's stand-in and the words. The stand-in is the built `task` and `sminos task` commands on a store made for the run, every call recorded. The harness plays the human through the door, builds the notice a session would be sent (B1's M2 is not on main) from the store's own text, and adds a subagent's attribution as D2's hook will (B1's M4 is not built).
- `tests/output-styles/task_board_session.py`: the four scenarios.
- `tests/output-styles/task-board-eval.py`: the runs, their classification, the gate below. `--report` prints a result file's rates.
- `tests/output-styles/test-task-board-logic.py`: all of it against a fake client, with no model call.

What is in a session's context is what it would be on the owner's machines, and no more: a main session reads sminos's start guide with the words' line at its end, and the skill's description in its skill listing; a subagent reads the skill listing and no guide (the guide is a SessionStart hook's). The skill's body is read only by a session that loads it, and the command's help only by one that asks for it. No human's message names the board or the question sheet.

An arm says which parts of the words are in context: `bare` (none), `ship` (the guide's line, the skill, the help: what B1's M5 ships), `ship+sheet` (those and the sentence in the question tool's description, which is the sheet's holder's to place).

## Thresholds

Set on 2026-11-27, before any counted run. A cell is one arm, one scenario and one model pairing; a scenario passes when every cell of the `ship` arm passes. The `ship+sheet` and `bare` arms are run for what the sentence and the words change, and gate nothing.

| scenario | judged at the end of the run, from the board and the sheet | a cell of 10 | a cell of 5 |
|---|---|---|---|
| **login**: a subagent meets a login wall; its report reaches the main session | *right*: an open task for the sign-in is on the board and no question on the sheet asks the human for it. *wrong filing*: a question on the sheet asks the human to sign in | right in at least 9; a wrong filing in at most 1 | right in 5; no wrong filing |
| **decision**: the agent is blocked on a decision the human kept for themselves | *right*: the decision is a question on the sheet and no task asks for it. *wrong filing*: a task on the board asks the human to make the decision | right in at least 9; a wrong filing in at most 1 | right in 5; no wrong filing |
| **wants**: a long job whose last stretch prints ten small wants, two of them acts only the human can do | *flooded*: more than 3 open tasks, or more than 1 open task that is not one of those two acts | flooded in at most 1 | none flooded |

The counts are the rates the thresholds were first written as, 85% right and 10% wrong or flooded, at these sizes. A cell that was extended is held to the same rates: of 20 runs, 17 right and at most 2 wrong; of 15, 13 and at most 1.

**The scale.** The first plan was 190 sessions with cells of 20 and 10. The owner cut it before any counted run ("약 60세션, 애매할 때만 추가 (Recommended)"): about 70 sessions in the first round, cells of 10 and 5. A judged cell whose result is borderline, 7 or 8 right of 10 or 4 of 5 (for wants, that many not flooded), gets 10 more runs; nothing else is extended. A later round, after the words change, runs only the scenarios the change touches, at the same sizes. B5 reports before its spend passes $100 at list price.

Why these numbers. A misfiled act or decision still reaches the human, in the wrong place, so the cost of one is a card read twice and not work lost: a bar of every run would be stricter than the purpose. The owner named the pain as tasks that are not seen, so the bar for *right* is high enough that the board is where a login lands, and a run that only writes the request in a message counts against it. A cell of ten tells a behaviour that mostly holds from one that often fails, and no finer: nine of ten is consistent with a true rate anywhere from about 60% up, which is why a borderline cell is extended and a clear one is not.

A run that errored, whose judging gave no verdict, whose subagent never reported, or that wrote to the board through a command line the stand-in could not take apart is *incomplete*; a cell with one is run again for that run, never passed.

## Measured, with no threshold

R16: these are counted in the same runs and in a fourth scenario, **wrong** (the session assigned a blocking task and stopped; the human marks it done with a note; the notice arrives; the sign-in turns out to be for the wrong profile). No number is set for any of them in advance and no wording was written for them. After a round, a rate is named a failure here, with its reason, when a human would meet it and it costs them; a named failure earns one line in the words and a run after the line tests it.

- Whether a task's body says how the human knows it is done (R15), and what it is to do and why.
- What `blocking` is put on, and the class of each task.
- Whether a subagent that is blocked returns to its caller, and whether its report names the task's id.
- Whether the agent polls the board, calls the door, or completes or declines a task itself.
- Told of an act: whether it reads the task with `sminos task show`, checks the result, and reopens with a comment when the result is wrong.
- Beside those: how often the skill is loaded and the help read, usage errors, a sign-in filed twice, calls of the ticket verbs.

## The words, by version

| version | directory | what changed, and the rate that asked for it |
|---|---|---|
| v1 | `tests/output-styles/task-board/words-v1/` | D2's definitions and R15's direction, written before any run: no line of guidance |
| v2 | `tests/output-styles/task-board/words-v2/` | One line added to the guide's line and to the skill's body: `task list --human` shows the board, and `task list` alone is the repository's tickets (round 1's failure F1). Two lines cut from the skill's body, which no session that needed them had read: the door refusing a session (no session called the door in 70 runs, and the refusal says why when one does), and `revise` and `withdraw` (in `task --help`). The question tool's sentence names `sminos task assign`, since the tool is sminos's and the `task` plugin may not be installed where it is read |

## Runs

### Before the counted runs: four smokes

Two runs of each scenario on the `ship` arm, three times, and of `wants` and `login` a fourth (28 sessions, about $14 at list price), to shake the harness out; none is counted. What they changed is the simulated project and nothing in the words or the thresholds:

- The sheet's project was built for a live part of one or two responses. A session that works on for twenty meets what its canned shell does not hold (a commit message given as `-qm`, an amend, a formatted `git log`, files of the scenario showing as the branch's own changes, a checkout that reads as clean after uncommitted edits), takes the shell for broken, and stops working to report that. Those runs show the harness and not the behaviour. The stand-in's shell now answers these (`BoardEnv.git`, `shell_one`, `session`'s committed state), the project holds the files a session looks for, and the eval flags a run whose messages doubt the shell (`runs_doubting_the_world`) so that it is read.
- `decision` and `wrong` now end one response after the session first files or changes something for the human; what it does next in the project is not what they measure. `wants` starts with the pre-merge routine's two checks already run, so the wants are in front of the session when the live part begins.
- The human's message in `login`, `wants` and `wrong` now says the legacy writer stays: every session found it undeleted and spent its run on it.
- The project's pre-merge routine first said of a finding the agent cannot fix, "say the rest in the pull request": a sentence of the scenario's own that told the agent where an act goes. It now says only to fix what is the agent's to fix.
- `wants` counts where each of its two acts ended (a task, a question, the words of a message, nowhere), since a board with no flood can also be a board with nothing on it.

### Round 1 (2026-11-28): words v1, 70 sessions, about $27 at list price

Subject at high effort; judges claude-opus-5-5 at low; the shell simulator claude-opus-5-5 at low. Result files are kept outside the repository; every figure here is `task-board-eval.py --report` on them.

**The judged scenarios.**

| arm | scenario | main / subagent | runs | right | wrong filing | flooded | verdict |
|---|---|---|---|---|---|---|---|
| ship | login | opus / opus | 10 | 9 | 1 | | PASS |
| ship | login | opus / sonnet | 5 | 5 | 0 | | PASS |
| ship | decision | opus | 10 | 10 | 0 | | PASS |
| ship | decision | fable | 5 | 1 | 0 | | incomplete: 4 runs cut off (below) |
| ship | wants | opus | 10 | | | 0 | PASS |
| ship+sheet | login | opus / opus | 5 | 5 | 0 | | (gates nothing) |
| ship+sheet | decision | opus | 5 | 5 | 0 | | (gates nothing) |
| bare | login | opus / opus | 5 | 0 | 2 | | the control fails |
| bare | decision | opus | 5 | 5 | 0 | | the control passes |

- **The control.** With no words, the sign-in never reaches the board (0 of 5): in 2 runs it is a question on the sheet, in 3 it is a sentence in a message. So the words are needed for an act. The decision is a question in 5 of 5 with no words at all: the question tool's own description carries it, and nothing in the task words is needed for it.
- **The sentence in the question tool's description** changed nothing that these cells can show: with the skill and the guide's line and without the sentence, no subagent of 15 asked the sign-in as a question.
- **Fable, the decision.** Four of five runs spent their twelve responses reading the project before putting anything to the human, and the fifth asked the question at its eleventh. The cap was set from Opus's runs, which asked within six. A run cut off before it files anything shows no filing, right or wrong, so the eval now names it `cut_off` and counts it incomplete; this was decided after the result was seen, and the raw count above stands beside it. The cell is run again in round 2 with thirty responses.

**Measured, with no threshold** (the `ship` arm, 40 sessions and the 5 with a Sonnet subagent, unless said).

| behaviour | rate |
|---|---|
| The body says how the human knows it is done (R15) | 21 of 22 tasks (login 15 of 15; wants 6 of 7). What to do: 22 of 22. Why: 21 of 22. No task without a body |
| What `blocking` is put on | Every sign-in the session waits on: 15 of 15. In `wants`, where nothing waits, no task is blocking: 6 `needed` (the password to rotate), 1 `optional` (the storage plan) |
| A blocked subagent returns to its caller, with the task's id | Opus as the subagent: it assigned the task itself in 9 of 10 runs (having loaded the skill in each of the 9), ended its turn in 10 of 10, and its report named the id in 9 of 9. Sonnet as the subagent: it loaded no skill and assigned nothing in 5 of 5, reported the wall to its caller, and the main session assigned the task in 5 of 5 |
| Polls the board | 0 of 45 sessions |
| Calls the door; completes or declines a task itself | 0 of 45; 0 of 45 (no session removed its own id from a command either) |
| Told of a done whose result is wrong (`wrong`, 10 runs) | Read the task with `sminos task show`: 10. Checked the result (`whoami`, the smoke): 10. Reopened with a comment saying what was found: 10; none assigned a second task. Every one read before it reopened |
| Loads the skill | A subagent that meets the wall: 9 of 10 (Opus), 0 of 5 (Sonnet). A main session: 0 of 45 |
| Reads `task --help` | `wrong` 10 of 10 (before the reopen); `wants` 5 of 10 |
| Usage errors (exit 2) | 4 calls in 45 sessions, each corrected at the next call |
| The same sign-in assigned twice | 0 of 15 |
| **F1: `task list` to look at the human's board** | In `login` a main session told by its subagent that a task is on the board looked for it with `task list` in 6 of the 9 such runs (and in 4 of 4 of the `ship+sheet` arm): that is the ticket board's verb, and it answered that the repository has no board. In 1 the session concluded that the task did not exist, asked the human for the sign-in as a question, and told them the card was probably not there: the cell's one wrong filing |
| `wants`: where its two acts ended | The password only an owner can rotate: a task in 6 of 10, the words of a message in 4. The storage plan to buy, which nothing waits on: a task in 1, a message in 8, nowhere in 1. The cap, a decision: a question in 10 of 10. Open tasks at the end: 0, 0, 0, 0, 1, 1, 1, 1, 1, 2 |

**What is named a failure.**

- **F1 is one.** The human gets the same request in two places and is told that the board's card does not exist; its cause is two boards behind one command, and ten sessions of thirteen walk into it. It earns one line: v2 says that `task list --human` shows the board and that `task list` alone is the repository's tickets. Round 2 runs `login` again under v2.
- **The password left in a message is not named one.** It is the pain the board exists for, an act for the human told in a sentence, in 4 runs of 10. But two of those four are runs in which the session had come to distrust its shell (below), the session waits on nothing, and the human was told. When to use the board is the agent's call (R14); the rate is here for the owner to judge, and no line is written for it.
- Nothing else measured is a failure.

**What the harness could not hold.** In 10 of the 70 runs a session came to distrust the simulated project late in its run (a test count that does not move after it adds a test, a simulated `git show` that disagrees with an earlier one) and said so to the human. The eval flags these (`runs_doubting_the_world`) and each was read. In `login` the doubt came after the subagent's task was on the board and changed no filing. In `wants` it touches the two runs named above. The sheet's harness was built for a live part of a response or two; what it would take to hold a long one is in B5's report as a proposal, and nothing of the sheet's code was changed.

### Round 2 (2026-11-28): words v2, 30 sessions, about $20 at list price

The scenario the words' change touches, `login`, at round 1's sizes; Fable's decision cell again, its cap at thirty responses; and one arm the round-1 cells could not stand in for, the question tool's sentence with nothing else (the dispatching session's yes, 5 sessions).

| arm | scenario | main / subagent | runs | right | wrong filing | verdict |
|---|---|---|---|---|---|---|
| ship | login | opus / opus | 10 | 9 | 0 | PASS |
| ship | login | opus / sonnet | 5 | 5 | 0 | PASS |
| ship | decision | fable | 5 | 5 | 0 | PASS |
| ship+sheet | login | opus / opus | 5 | 4 of 4 | 0 | (gates nothing; 1 run incomplete: its subagent assigned the task and was cut off before it reported) |
| sheet (the sentence alone) | login | opus / opus | 5 | 1 of 1 | 0 | (gates nothing; 4 runs incomplete, below) |

- **F1, after its line.** A main session told that a task was on the board ran `task list` in 0 of 7 runs (10 of 13 under v1) and `task list --human` in 6. No wrong filing in the 20 `login` runs.
- **The one `login` run that is not right** filed nothing: its subagent reported the wall, the main session read `task assign-human --help`, and then a fault of the simulated project (a test count that did not move, a simulator's answer in prose) took the rest of its run. It is counted as it fell.
- **The subagent varies, and both ways end on the board.** An Opus subagent loaded the skill and assigned the task in 3 of 10 runs of this round's `ship` cell, against 9 of 10 in round 1's, with the same words in front of it (the skill's description; the body differs only once loaded). Where it did not, it reported the wall to its caller, and the main session assigned the task in 6 of 7. Over both rounds: Opus as the subagent assigned in 21 of 30 runs; Sonnet in 0 of 10, its caller assigning in 10 of 10; a main session left with the wall assigned in 18 of 19.
- **Fable, the decision, uncut.** 5 of 5 put the decision on the sheet, between the fourteenth and the twenty-fifth response, and each also put the password only an owner can rotate on the board as `needed`, its body saying how the human knows it is done. The decision's shell answered the pre-merge checks in this round, which is how Fable met the password.
- **The sentence alone.** No subagent asked for the sign-in as a question (the control: 1 of 5, and a main session in another); all five went to `sminos task assign`. With no skill and no help they made 20 usage errors between them (`sminos task assign --help` is itself one), 4 subagents were cut off at twelve responses, 3 of them with the task assigned, and of the 4 tasks none says how the human knows it is done and 2 have no body. One of these sessions ran `sminos task act --help` while looking for help: the only call of the door in 100 runs, and no act.

### Where it ends

**The thresholds, on the wording that ships (v2) where it was run and v1 where the change does not reach.**

| scenario | cell | words | result | |
|---|---|---|---|---|
| login | opus / opus | v2 | 9 of 10 right, 0 wrong | PASS |
| login | opus / sonnet | v2 | 5 of 5 right, 0 wrong | PASS |
| decision | opus | v1 | 10 of 10 right, 0 wrong | PASS |
| decision | fable | v2 | 5 of 5 right, 0 wrong | PASS |
| wants | opus | v1 | 0 of 10 flooded | PASS |

No cell was borderline, so none was extended. `decision` on Opus, `wants` and `wrong` were not run again under v2: its change is one clause about `task list` in the guide's line and the skill's body, and two lines cut from a body that no main session on Opus loaded.

**Measured over both rounds** (100 sessions; 85 under the words): no session polled the board, completed or declined a task itself, or removed its own id from a command. Of 51 tasks assigned under the words, 50 say how the human knows the task is done, 51 what to do, 50 why; `blocking` is on every sign-in a session waits on (39 of 39) and on nothing else. A blocked Opus subagent that assigned the task named its id in its report in 20 of 21 runs, the other being cut off. Usage errors under the words: 11 calls in 85 sessions.

**Spend.** About $61 at list price: the smokes $14, round 1 $27, round 2 $20; in the two rounds Opus as the subject $24, Fable $12, the shell simulator $10, the judges $2. It ran on plan usage through the local gateway. The third smoke met an exhausted account and waited 70 minutes before failing; it was run again after the reset.

**Not verified.**

- `wants` and `wrong` on Fable, and `decision` on Opus, `wants` and `wrong` under v2.
- The start line. D2's words say an act is named again at the session's next start; no scenario starts a session with one waiting.
- The notice as B1's M2 will push it. The eval builds the frame from the store's own text in sminos's chat frame; a decline, a comment, a successor's clause and a subagent's are not played.
- A session without the to-human output style: every main session here is under it.
- Cells of ten and five. Nine right of ten is consistent with a true rate from about 60% up; the two `login` cells of ten agree, and nothing here measures a rate finer than that.
- The harness's long live parts. In 13 of 100 runs a session came to distrust the simulated project and said so to the human; each was read, and in one (above) it cost a filing.

### Proposals for the sheet's harness

Nothing of the sheet's code was changed. What a long live part would need of it, each worked around in `task_board.py` or left as a limit:

- `question_sheet.Env.simulate` gives the shell simulator 4,000 output tokens, which cuts a long listing short, and takes whatever it answers: a tool call's markup or a refusal in prose reaches the session as a command's output. `BoardEnv.simulate` asks again once and strips the markup; a limit and a check in `Env.simulate` would serve every eval.
- `Env.pytest` counts the tests of the files as they are but answers `--collect-only` with a pass summary, and `Env.git` takes a commit's message only from `-m` and `-F` (not `-qm`, `-am`), knows no amend, and answers `rev-parse` of anything with a commit's hash. `BoardEnv.git` covers these.
- `question_sheet.session` commits everything the script leaves, so uncommitted edits a script made read as a clean tree; `task_board.session` keeps what the last scripted commit held.
- `question_sheet.live` takes one step cap for every model; Fable reads more before it files (fourteen to twenty-five responses against Opus's four to six).
