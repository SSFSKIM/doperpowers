---
name: progress-report
description: Use when your human partner asks for an explanation — of changes an agent implemented that they did not watch, or of a concept they want to understand — including /progress-report, ELI5-style requests, "explain this", "walk me through what changed", "what is X", "help me understand".
---

# Progress report

An explanation succeeds when your human partner can act on the subject
without you: make the next product or technical decision about a change,
or reason with a concept in a case you never mentioned. Hold the draft
to that test before sending: one that equips them for no specific
decision or case is missing its mechanism or its decisions.

Your reader is a capable adult who lacks this particular context.
Simplify by removing the incidental, never the mechanism. Asked to
"explain like I'm five", agents produced emoji headers, cartoon framing
("a magic notebook"), and an analogy — blocks combined in any order give
the same shape — that taught the wrong mechanism and left the reader
unable to predict anything. Plain register and a real mechanism are what
make an explanation simple to use.

Length follows the request. Asked for a brief answer, give one short
paragraph: the mechanism in a sentence or two and the boundary most
likely to matter to them. The parts below are what a full explanation
covers.

## A change — control over it

Your human partner owns the change now, and a code walkthrough alone
leaves them owning something they cannot steer. The explanation carries:

1. **What behaves differently**, from where they stand — the visible
   effect first, then how the code achieves it and where it lives.
2. **Decisions made on their behalf** — each choice that had a real
   alternative (a default, a fallback, a boundary, what was left out),
   with the reason, so they can overrule it.
3. **Limits and risks** — what it does not cover, what is unverified,
   what would break it.
4. **How to see it for themselves** — the behavior to try, the test,
   the file to open.

Mechanical churn (version bumps, renames) gets a clause at most.

## A concept — intellectual control over it

1. **The problem it exists to solve** — what goes wrong without it.
2. **The mechanism** — why it works, stated so they could reconstruct
   it. One concrete example traced step by step does more than general
   description.
3. **The boundaries** — what it guarantees and what it does not, where
   it breaks, what it is commonly confused with.
4. **What it means for them** — when they named a situation or goal,
   the decision criteria the concept implies for it.

## Clarity

- Define a term at first use, or don't use it.
- Use an analogy only when its structure matches the mechanism, and say
  where the match ends. Otherwise state the thing literally.
- Every example and fact you cite (who uses X, what a number is) must be
  one you are sure of; a plausible wrong example corrupts the model you
  are building for them.
- Draw a diagram, table, or step sequence when the structure is spatial
  or temporal — state over time, data flow, before and after.
