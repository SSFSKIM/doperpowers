# Task Board B5: what agents are told (X7), as proposed

> Child B5 of `docs/doperpowers/specs/2026-11-27-task-board-design.md` (parent pin `a99ce15dd`); contract X7. This is the wording B1's M5 ships and the sentence handed to the question sheet's holder, each with the evidence it rests on. The runs, their thresholds and every rate are in the ledger beside this file, `2026-11-27-task-board-b5-ledger.md`; the texts themselves are the files of `tests/output-styles/task-board/words-v2/`, which the eval reads, and are copied here.

The words describe the board and what its verbs do (R14). They carry one direction (R15: the body says how the human knows it is done) and one line of guidance, for the one failure the runs measured (R16).

## Where each text loads, and who reads it

| text | loads | read by |
|---|---|---|
| the guide's line | at a session's start, in sminos's start guide (`guide_text`) | a main session that is a member on an enrolled machine. **Never a subagent**: the guide is a SessionStart hook's |
| the skill's description | in every session's skill listing, on every turn | every session and every subagent where the `task` plugin is installed |
| the skill's body | when a session invokes the skill | in the runs: a subagent that met a login wall, in 23 of 30 runs with Opus as the subagent and 0 of 10 with Sonnet; a main session on Opus in none of 74, on Fable in 3 of 10 |
| the help text | when a session runs `task --help` or `task <a human's verb> --help` | in the runs: a main session about to assign or reopen, every time (below) |
| the question tool's sentence | in the question tool's description, on every turn of a session that has the tool | every session and subagent with the tool, whether or not the `task` plugin is installed |

So a subagent learns of the board from the skill's description alone, and a main session from the guide's line and the help. The description and the guide's line each carry D1's line for that reason, and the body carries nothing either of them needs.

## The guide's line

One line, the last of the start guide:

    Your human partner has a task board on this machine: `task assign-human` puts on it something only they can do in the world (a login, a permission, a purchase, a merge), returns at once, and what they do about it reaches you as a message. `task list --human` shows the board; `task list` alone is the repository's tickets, another board. `task --help` lists the verbs; the task:human-tasks skill describes the board.

| part | evidence |
|---|---|
| The board exists, what goes on it, the verb | The control: with no words, the sign-in reached the board in 0 of 5 runs (a question in 2, a sentence in a message in 3). With the words, a main session whose subagent reported the wall without assigning anything assigned the task itself in 18 of 19 such runs, having read nothing but this line and the help (the nineteenth read the help and was then taken up by a fault of the simulated project) |
| "returns at once", "reaches you as a message" | Definitions (D2). No session polled the board or waited on a command in 100 runs, the control's included: the runs cannot say that these words are why |
| **`task list --human` shows the board; `task list` alone is the repository's tickets** | **The one line of guidance (F1).** Under v1 a main session told by its subagent that a task was on the board looked for it with `task list` in 10 of 13 runs; the ticket board's verb answered that the repository has no board, and in 1 run the session concluded the task did not exist, asked for the sign-in again as a question, and told the human the card was probably not there. With the line: 0 of 7 such runs (6 ran `task list --human`), and no wrong filing in 20 |
| The two pointers | The help was read before every assign a main session made (19 of 19) and before every reopen (10 of 10). The skill: a main session on Opus never loaded it and one on Fable did in 3 of 10; the pointer costs eight words |

## The skill: `task:human-tasks`

    ---
    name: human-tasks
    description: The human's task board — what a task for your human partner is (something only they can do in the world: log in, grant a permission, buy, merge), its classes, the `task` verbs that assign and change one, and how what they did comes back. For work that needs the human to do something, and for a task you assigned that they completed, declined or commented on.
    ---

    # The human's task board

    A task is one thing a session asks its human partner to do in the world:
    log in, grant a permission, rotate a key, buy, review and merge a pull
    request. It is their to-do, listed on this machine's board with every other
    session's until they close it; the session that assigned it is where the
    outcome is sent. A decision or an answer you need from them is a question,
    not a task; a judgment is a task only when giving it is itself an act in
    another system (approving a pull request).

    `task assign-human --class <class> --title "..." --body-file -` adds one
    and returns at once: nothing waits on it. `task list --human` shows the
    board; `task list` without `--human` is the repository's tickets, the
    agents' own backlog and another board. `task --help` has every verb and
    flag.

    - The body says what to do, why, and how the human knows it is done.
    - The class is `blocking` (you cannot go on without it), `needed` (it must
      be done at some point) or `optional`. The board lists blocking first, and
      a blocking task's completion wakes a session that has stopped.
    - What the human does with a task (done, declined, a comment) reaches the
      session that assigned it as a message naming the task, and is named again
      at that session's next start. Their words are read with
      `sminos task show t<n>`.
    - "Done" is the human's word about their step. `task reopen t<n> --comment
      "..."` puts a done task back on the board.

| part | evidence |
|---|---|
| The description | What a subagent has. With it, an Opus subagent that met the wall loaded the skill and put the sign-in on the board in 21 of 30 runs and otherwise reported the wall to its caller; a Sonnet subagent always reported (10 of 10), and its caller assigned. No subagent of 40 asked for the sign-in as a question; with no words 1 of 5 did, and the main session did in another |
| D1's line (a task, a question, a judgment) | The decision was a question and never a task in every completed run of every arm (26 of 26), the control included: the question tool's own description carries a decision. Fable, in the same run, put the decision on the sheet and the password only an owner can rotate on the board (5 of 5). The line is kept as the definition of what the board holds (D1, binding); the runs show no filing it changes |
| "The body says what to do, why, and how the human knows it is done" (R15) | The owner's direction. Of 51 tasks assigned under the words, by a subagent that had read this line or by a main session that had read the help text, which carries the same words on `--body-file`, 50 say how the human knows the task is done and none lacks a body. Of 4 assigned under the question tool's sentence alone, with neither to read, none says it and 2 have no body |
| The classes, and what `blocking` does | `blocking` was put on every sign-in a session waited on (39 of 39) and on nothing where nothing waited: the password to rotate was `needed` in 11 of 11, the storage plan `optional` |
| How the human's act comes back; `sminos task show` | Told of a done by the notice, 10 of 10 sessions read the task with `sminos task show` before anything else. The notice names the command itself, and none of those sessions had loaded the skill: the line is D2's definition and is not what produced the reading |
| "Done" is the human's word; `reopen` | 10 of 10 checked the result, found the sign-in on the wrong profile, and reopened with a comment saying what they found. They had the verb from `task --help`, not from the skill |
| `task list --human` | F1, as in the guide's line; here for the subagent, which does not read the guide |

**Cut from D2's list**, each for the same reason, that no session that needed the line had read it:

- *The door refuses any agent session, so the human's acts are the human's alone.* No session completed or declined a task itself, called the door to act, or removed its own id from a command, in 100 runs; the sessions with most reason to, the ten told of a done whose result was wrong, had not read the skill. The refusal says why when a session meets it (`sminos task done` in a session exits 3 with the reason).
- *`revise` and `withdraw`.* They are in `task --help`; the skill says what the reading model cannot derive.

## The help text

What `task --help` prints for the human's board, and `task assign-human --help` (and the other human's verbs' `--help`) in full:

    The human's task board (this machine's, kept by sminos; these work in any directory):

      task assign-human --class blocking|needed|optional --title "..." [--body-file F|-] [--due YYYY-MM-DD] [--tag x]...
            a task for the human; prints its id and the line they will see, and returns at once
            --class      blocking: you cannot go on without it; needed: it must be done at some point; optional
            --body-file  the body, Markdown, from a file or from standard input (-): what to do, why, and how the
                         human knows it is done
      task show t7 [--json]            the task whole: its body, its comments, what the human did and their words
      task list --human [--mine] [--closed|--all] [--json]    the board, blocking first
      task revise t7 [--title ...] [--body-file F|-] [--class ...] [--due ...|--no-due] [--tag x]... [--no-tags]
            change a task you assigned; the human sees it marked Updated
      task comment t7 "..." | --body-file F|-    a comment on an open task
      task withdraw t7 [--reason "..."]          take back a task you assigned
      task reopen t7 --comment "..."             put a task the human marked done back on the board, saying why

Evidence that it is read: a main session read the help before every assign it made (19 of 19 runs, `task assign-human --help` in most) and before every reopen (10 of 10). As built both fall short: `task assign-human --help` is a usage error (the flag is passed to `sminos task assign`, which has none), and `task --help` names the verbs with no flag. The eval's stand-in prints this text in their place. Three things for M5, seen in the runs:

- The text belongs where `task <verb> --help` prints it for each of the human's verbs; a session reaches for that form first.
- In `task --help` it should come before the ticket verbs' list or be short enough to survive `| head -30`, which a session piped it through.
- `--body "…"` is taken for `--body-file` by the parser's prefix matching, and the text is then read as a file's name (`File name too long`): 2 sessions of 85 under the words lost calls to it, and 3 of the 5 with no help to read.

## The question tool's sentence, for the sheet's holder

One sentence, proposed as the second paragraph of the tool's description:

    Something only the human can do in the world (log in, grant a permission, buy, merge) is not a question: it is a task for their task board (`sminos task assign`).

It names `sminos task assign` and not `task assign-human`, since the tool is sminos's and the `task` plugin may not be installed where its description is read.

**Its evidence** is the arm that has the sentence and nothing else (5 runs: no guide's line, no skill, no help). No subagent asked for the sign-in as a question, where with no words at all 1 of 5 did and a main session did in another; every one went to `sminos task assign`. The same arm shows that the sentence does not carry the command: `sminos task assign --help` is a usage error and `sminos help` is the whole CLI's, so the five sessions made 20 usage errors between them, 4 subagents spent their twelve responses on the command (3 had assigned by then), and of the 4 tasks none says how the human knows it is done.

Where the skill is listed the sentence showed no effect: no subagent asked the sign-in as a question with it (10 runs) or without it (30). So it earns its place for a session that has the question tool and no `task` skill in its listing, and adds nothing these runs can show elsewhere; it costs one sentence in a description every session holds on every turn. Placing it is the holder's call. If it is placed, `sminos task assign` needs a `--help` of its own.

## What M5 should know beside the words

- **A subagent never reads the guide's line.** D2 said the words reach agents in three places; a subagent has two of them at most. The composite's D2 now says so.
- **The fix at F1's cause is being made** in the `task` command, by the session that dispatched B5: `task list` where the repository has no ticket board will name `task list --human`. The guide's line stays either way: in a repository that has a ticket board, `task list` prints tickets and no error.
- **The guide's line names `task`**, as R7 has agents use it, and the guide is sminos's: on a machine with sminos and without the `task` plugin the line names a command that is not there. M5 prints the line only where `task` is installed, or names `sminos task assign` there.
