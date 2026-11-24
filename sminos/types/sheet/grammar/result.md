# A call's result (contract X7; plan I6)

The tool's result is text. Its first line has a fixed grammar, so a stored call is read from its input and this
line alone, long after the sheet's record is gone.

    first-line = sentences / "Nothing done." / "Outcome not known yet."
    sentences  = sentence *( " " sentence )
    sentence   = added / revised / withdrew              ; in this order, each at most once
    added      = "Added " item *( ", " item ) "."
    revised    = "Revised " ritem *( ", " ritem ) "."
    withdrew   = "Withdrew " id *( ", " id ) "."
    item       = id [ " (entry " n ")" ]
    ritem      = id " (" [ "entry " n ", " ] "revision " n ")"
    id         = "q" 1*DIGIT        n = 1*DIGIT

- The sentences: what a call changed. Ids stand in the order of the call's entries; `n` is an entry's place in
  `ask`, from 1, and every `item` and `ritem` carries it exactly when some entry or withdrawal of the call was
  refused.
- `Nothing done.`: every part of the call was refused, or the call was foreclosed. The sheet is as it was.
- `Outcome not known yet.`: neither the call's step nor its settling answered. The second line reads `The sheet
  did not answer. Do not repeat this call: what it did will be told to you.` A reader draws no ids for such a call
  and does not look for the notice that follows it.

A second line, present when anything was refused, reads `Not done: ` and one clause per refusal, each closed by a
period. A last line, when no surface can show the questions:
`No surface can show these questions right now; they wait on the sheet and show when one returns.`

A denial (the whole call refused before any step) is the engine's error result and has none of these lines.

## The pattern a reader matches

The first line, whole (ECMAScript and Python `re` alike):

    ^(?:Nothing done\.|Outcome not known yet\.|Added q[0-9]+(?: \(entry [0-9]+\))?(?:, q[0-9]+(?: \(entry [0-9]+\))?)*\.(?: Revised q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\)(?:, q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\))*\.)?(?: Withdrew q[0-9]+(?:, q[0-9]+)*\.)?|Revised q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\)(?:, q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\))*\.(?: Withdrew q[0-9]+(?:, q[0-9]+)*\.)?|Withdrew q[0-9]+(?:, q[0-9]+)*\.)$

Parsed, as `result.examples.json` holds it under `parsed`:

    { "form": "sentences", "added": [ { "id", "entry"? } ], "revised": [ { "id", "entry"?, "revision" } ],
      "withdrew": [ id ] }
    { "form": "nothing" }           { "form": "unknown" }

## The clauses of `Not done:`

    entry <n>, the reference <path> could not be read: <reason>
    entry <n>, two options share the label "<label>"
    entry <n>, an option's preview needs a single-select question
    entry <n>, multiSelect needs options
    entry <n>, lines must be [a, b] with 1 <= a <= b
    entry <n>, <id> is not open (<how> at <HH:MM>)             how: answered, dismissed, withdrawn, never asked
    entry <n>, <id> was asked by <the main conversation | the subagent <name>>; only its asker revises it
    entry <n>, the sheet holds 500 open questions
    <id> is not open (<how> at <HH:MM>)
    <id> was asked by <...>; only its asker or the main conversation withdraws it
    the sheet could not be written (<why>); call again                 a foreclosed call's one clause

A label in a clause is cut at 200 characters; a time is the session machine's local time.
