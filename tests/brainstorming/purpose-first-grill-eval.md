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

## 2026-09-09 revision: stopping rule, criteria as formed, reading the reaction

A second reading of the change found three gaps against its own intent: the
"frontier empty → done" rule was left standing beside the new warning, so a
reader could satisfy the rule and ignore the warning; the sentence "how good
the result can be is bounded by how well its purpose is defined" generalized
toward upfront definedness, when the point to keep is clarity of purpose and
criteria that stay revisable; and the partner's taste was still to be
*interviewed* for, when much of it only shows in reaction to something
concrete. Three edits, list of purpose questions unchanged:

- "An empty frontier ends a round, not the grill." The done-criterion moved
  into the depth paragraph: purpose and criteria mature enough to justify the
  choices being made now, every branch visited, remaining unknowns empirical
  and each named with the move that resolves it.
- "What the result can be is set by how clearly its purpose and the criteria
  for a good one are held — criteria that are formed as much as found, and
  that move when the work reveals a possibility nobody had in view."
- "Put concrete things in front of them — a scene of it in use, alternatives
  that differ in what they treat as central — read the criterion out of their
  reaction, and propose again; options exist to reveal what matters, not to
  confine the answer to them. The labor of defining the problem is yours."

Snapshot: `c586c072a953b4e42ba752f4e4012e3f988e2c66107cfe1d2143ffe5f1a21c1d`
(2,701 words; the 2026-09-08 prose pass had landed at 2,298).

**First-round scenario, re-run** (same brief and rubric as above):

| Arm | Model | best | must-not | propose |
|---|---|---:|---:|---:|
| Revised | sonnet | 5/5 | 5/5 | 5/5 |
| Revised | opus | 5/5 | 5/5 | 5/5 |

Four of five opus reps additionally bring two or three rival pictures of the
initiative and ask for the reaction rather than the pick ("not a menu to pick
from; I want to read the criterion off your reaction", "which makes you nod,
and what's wrong with the other two"). Sonnet reps offer candidate anti-goals
and framings to react to but rarely author a scene themselves.

**Stopping-rule scenario** (new). The agent is shown a grill three rounds in:
every decision-level question (scope, what counts as learned, capture,
retrieval, staleness, storage, concurrency, relationship to the existing
store) has an answer, no branch is open, and the partner has said nothing
beyond the one-sentence brief and those answers. Classify DONE or CONTINUE.
Sonnet, 5 reps per arm:

| Arm | DONE | CONTINUE | Continuation anchored on purpose |
|---|---:|---:|---:|
| Before (`283d2b5c…`) | 3 | 2 | 0/5 |
| Revised (`c586c072…`) | 0 | 5 | 5/5 |

Before-arm DONE reasons cite the rule verbatim ("every branch on the tree has
a settled answer… grinding further would violate 'don't grind'"); its two
CONTINUEs ask about injection caps and migration. Revised-arm reasons name
what was never asked — "the purpose-level frontier, what this must not
become", "the gap at exactly the word doing the work in the brief:
'compounds'", "purpose was never actually probed — what a great entry looks
like" — alongside the same mechanism gaps.

**Regression.** Authorized-technical PROCEED scenario against the revised
snapshot: 5 proceed / 0 pause.
