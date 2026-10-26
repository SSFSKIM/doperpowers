---
name: present
description: Use when your human partner wants to understand something end to end — work an agent shipped, a design you discussed, a spec, code someone else wrote, or any idea — and invokes /present.
disable-model-invocation: true
---

# Present

Write your human partner an explainer article, as an HTML page, that
leaves them understanding its subject end to end. The subject is what
they named; named nothing, it is what the conversation has been about —
the work just shipped, the design just discussed. It can be anything:
work an agent did while they were not watching, a design, a spec, code
someone else wrote, an idea from any field.

## Thorough

Thorough means the chain has no gap: every step from the problem to the
outcome is there, and every part is explained before the reader needs
it. It does not mean everything the source contains. A detail off that
chain goes in when it changes what the reader would predict or decide.

## Understandable

Write from where the reader stands, not from where your source does:
start from what they already see of the subject (a command they type,
what it prints), and explain each term they do not have yet — the
source's vocabulary, names coined in the session, the field's jargon —
before its first use. Name code only with what it does, and keep
`file:line` out of the sentences. Simplify by removing the incidental,
never the mechanism; compare to something familiar when its structure
matches the mechanism, and say where the match ends.
