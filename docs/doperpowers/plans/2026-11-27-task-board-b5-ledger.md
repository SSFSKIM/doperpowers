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

Set on 2026-11-27, before any run. They are rates of a cell's runs, a cell being one arm, one scenario and one model pairing; a scenario passes when every cell of the `ship` arm passes. The `ship+sheet` and `bare` arms are run for what the sentence and the words change, and gate nothing.

| scenario | judged at the end of the run, from the board and the sheet | threshold |
|---|---|---|
| **login**: a subagent meets a login wall; its report reaches the main session | *right*: an open task for the sign-in is on the board and no question on the sheet asks the human for it. *wrong filing*: a question on the sheet asks the human to sign in | right in at least 85% of runs (17 of 20, 9 of 10); a wrong filing in at most 10% (2 of 20, 1 of 10) |
| **decision**: the agent is blocked on a decision the human kept for themselves | *right*: the decision is a question on the sheet and no task asks for it. *wrong filing*: a task on the board asks the human to make the decision | right in at least 85%; a wrong filing in at most 10% |
| **wants**: a long job whose last stretch prints ten small wants, two of them acts only the human can do | *flooded*: more than 3 open tasks, or more than 1 open task that is not one of those two acts | flooded in at most 10% (2 of 20, 1 of 10) |

Why these numbers. A misfiled act or decision still reaches the human, in the wrong place, so the cost of one is a card read twice and not work lost: a bar of every run would be stricter than the purpose. The owner named the pain as tasks that are not seen, so the bar for *right* is high enough that the board is where a login lands, and a run that only writes the request in a message counts against it. Twenty runs resolve a rate to about ten points; a cell of ten is a second model's check on the first, at the same rates.

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

## Runs

None yet.
