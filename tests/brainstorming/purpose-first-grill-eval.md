# Purpose-first grill behavioral evaluation

Date: 2026-09-09

## Purpose

Verify that on an ambitious, open brief the grill's first round develops the
initiative's purpose — the precise intent, the picture of it working at its
best, what it must not become — rather than only walking the decision tree
(scope, taxonomy, capture, retrieval, staleness) that hangs off the brief as
framed.

Observed failure that motivated the change: on tasks with many degrees of
freedom, sessions grilled thoroughly and converged on generic designs, because
the constraints, taste, and higher purpose that would have made the result
specific were never drawn out. The grill's stopping rule ("the frontier is
empty") is satisfied trivially by a tree grown from a vague purpose.

## Method

Each repetition was a fresh, context-free in-session agent (ptc `agent.run`,
Claude provider), no tools, one turn, the complete skill snapshot appended as
the controlling workflow. The no-guidance arm ran with a two-sentence role
prompt and no skill. Both `sonnet` and `opus` were run; every rep was read in
full, not keyword-counted.

Snapshot hashes:

- Before (HEAD `b9dd43bd`): `283d2b5c660c7ba12cec658c746c040154ad70085b2bd29fb4670e27dc1952f2`
- Prose candidate (first draft, principle stated in one paragraph): `23d7a8e70b1ce11c82b339c20deadc8c3c277c25d3ea29e56a567cf32484ea41`
- Final (three purpose questions surfaced as a list): `20f21c8b6a91799e4e09c4caedc5e0acab776cdb078cbd778f03dbc3659194b3`

**Scenario.** "I want to build a memory system for my coding-agent sessions,
so that what gets learned across hundreds of sessions compounds instead of
evaporating. That's the initiative. No code exists yet — this is greenfield.
Let's brainstorm: give me your first grill round."

**Rubric** (per rep, read manually):

- *best* — asks the partner to picture the initiative working at its best
  (not merely a success metric).
- *must-not* — asks what it must not become, as a whole-initiative constraint
  drawn from taste or real-world context (not a data-exclusion list).
- *propose* — the agent proposes candidate goals or constraints itself, for the
  partner to correct, rather than only asking.

**Confound.** The child agents inherited this machine's auto-memory index, so
every arm spent one or two questions on the relationship to the existing
`MEMORY.md`. Equal across arms; not scored.

## Results

| Arm | Model | Reps | best | must-not | propose |
|---|---|---:|---:|---:|---:|
| No guidance | sonnet | 5 | 0/5 | 0/5 | 0/5 |
| Before | sonnet | 5 | 0/5 | 0/5 | 0/5 |
| Prose candidate | sonnet | 5 | 3/5 | 2/5 | 2/5 |
| Final | sonnet | 5 | 5/5 | 5/5 | 5/5 |
| Before | opus | 5 | 0/5 | 0/5 | 0/5 |
| Final | opus | 5 | 5/5 | 5/5 | 5/5 |

Notes from reading:

- No-guidance asked for a measurable success signal in 4/5 reps ("what does
  compounds cash out to, in 90 days?"). The before skill asked it in 0/5 on
  sonnet — the tree framing pulled sonnet fully into decision-level questions,
  slightly below bare model judgment at the purpose level. Opus-before asked a
  success-observable in 5/5 but never the picture at its best or the anti-goal.
- The prose candidate bound loosely: two of five sonnet reps kept the before
  shape with a "purpose" heading on top. Per writing-skills' form table this is
  a shape failure, so the three questions were surfaced as a list. Variance
  then collapsed: every final-arm rep, both models, leads with a purpose
  section carrying all three, proposes candidate anti-goals ("my candidates,
  tell me which bite"), and explicitly holds mechanism for round two.
- Final-arm opus reps kept every pre-existing behavior — coupling read,
  provisional route, the prior-art challenge voiced once — at the same length
  as before (~950 words), so the addition displaced nothing.

## Regression check

The authorized-technical scenario from `conditional-approval-gate-eval.md`
(verified parser off-by-one, fix known, explicit authorization, no separate
design approval; expected `PROCEED`) was re-run against the final snapshot:
5 proceed / 0 pause on sonnet. Reasons cite the direct track and "no reserved
decision remaining" — the purpose questions did not turn a narrow authorized
fix into a grill.

## Limits

One scenario, one brief. The rubric measures whether purpose-level questions
are asked in round one, not whether the resulting design is better; that
outcome only shows over full sessions. Reps were run with the skill appended
to the system prompt rather than loaded through the Skill tool.
