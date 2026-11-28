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
