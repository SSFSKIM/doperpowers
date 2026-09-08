---
name: experimental-context
description: experimental context mode — /experimental-context keeps this session's governing intent verbatim across compaction as keyed <revisit> entries, /experimental-context off turns it off
disable-model-invocation: true
---

You are in EXPERIMENTAL-CONTEXT mode.

A compaction summary keeps the mechanics of the current work and loses the
reasons behind it; a summary of a summary loses them faster. The transcript,
by contrast, keeps every message verbatim. This mode stores what a summary
drops in the transcript under keys, and a hook re-injects the latest value per
key after every compaction and on resume — you never have to go and look.

Write an entry anywhere in a normal message, outside a code fence:

    <revisit key="goal">...</revisit>

Re-emit a key when the fact behind it changes; the latest value wins. Retire
one with `<revisit key="handles" retired="true"/>`. Keys are short topic slugs.
The first line of a value is its summary — lead with what matters.

Worth a key: the governing goal in your human partner's own words and who it
serves; standing rules and source-of-truth pointers; standing directives (what
may not happen without being asked); decisions, with the alternatives rejected
and why; questions still owed to your human partner; live handles (worktrees,
PRs, agent ids). Not worth one: progress — git and ledgers hold it.

If this turn begins an initiative and no goal key exists, write one now. Each
injected entry shows when it was set and how many compactions ago: an old goal
is expected; an old handles entry is a reason to re-verify before use.

The mode holds across compaction and resume until your human partner types
`/experimental-context off`. If this invocation carried `off`, the mode has just ended.
