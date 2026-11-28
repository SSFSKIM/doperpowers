# The texts (X6; the execution document's §5)

Every text the board writes for an agent is built from these fixed words, a task's id, the outcome's word and a
subagent's id, and nothing else: no title, no body, no agent's comment, no subagent's name, no alias, no note of
the human's (D5). `texts.examples.json` holds an example of each form, with the fields it was built from.

    id      = "t" pos
    pos     = %x31-39 *DIGIT                       ; a positive integer, no leading zero, no cap
    word    = "marked " id " done" / "declined " id / "commented on " id
    agent   = 1*128( ALPHA / DIGIT / "_" / "." / "@" / "-" )

## The notice (`[tasks v1]`, from the program `tasks`)

    notice-asker     = "[tasks v1] The human " word ", a task you assigned. Read it: sminos task show " id
    notice-successor = "[tasks v1] The human " word ", a task assigned by the conversation this one replaced at"
                       " a /clear. Read it: sminos task show " id
    notice-subagent  = "[tasks v1] The human " word ", a task your subagent " agent " assigned. Read it: sminos"
                       " task show " id

The message to a running subagent is `notice-asker`. Which clause a notice takes: the target reached through a
successor's pair (`via: "cleared"`), the successor's, whether or not a subagent assigned the task; else, for a task
that names a subagent, the subagent's; else the asker's. The id after `show` is the word's.

A reader recognizes one (ECMAScript and Python `re` alike, whole):

    ^\[tasks v1\] The human (?:marked (t[1-9][0-9]*) done|declined (t[1-9][0-9]*)|commented on (t[1-9][0-9]*)), a task (?:you assigned|assigned by the conversation this one replaced at a /clear|your subagent [A-Za-z0-9_.@-]{1,128} assigned)\. Read it: sminos task show (t[1-9][0-9]*)$

## The ended line (to the log of the project the thread ended in, no addressee)

    ended = "tasks: " id " was " ( "completed" / "declined" / "commented on" ) "; the conversation that assigned"
            " it has ended. It is on the board: sminos task show " id

## The start line (the SessionStart hook's, from the store)

    start      = [ count ] [ LF ] [ acted ]          ; count when the target has open tasks, acted when outcomes
                                                     ; wait; LF only between the two
    count      = "Tasks you assigned to the human: " n " open (" n " blocking)."
    acted      = "The human acted on tasks you assigned: " word *( "; " word ) [ more ] ". Read one: sminos task"
                 " show " id
    more       = " (and " n " more: sminos task waiting --mine)"
    n          = 1*DIGIT

`acted` names the first twenty waiting outcomes of the target's tasks by the store's `seq`, and `more` counts the
rest; the id after `Read one` is the first outcome's task. With neither part the start line is empty.

    fork = "This conversation is a fork: the tasks the conversation it was forked from assigned to the human"
           " stay with that conversation, and what the human does on them is told there, not here."

`fork` is printed after the start line, on a line of its own, at a start whose source is `fork`, when the store
holds any open task.

## What `remind` prints

    remind = keys LF [ start LF ] [ fork LF ]
    keys   = [ okey *( " " okey ) ]                  ; an empty line for none
    okey   = id "." pos                       ; the outcome's task, then its number

The first line is the keys of the outcomes `acted` names, in its order, which the hook hands to
`sminos task shown --keys` once the rest is printed; the hook prints everything after it.
