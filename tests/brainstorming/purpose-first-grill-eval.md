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

## 2026-09-09 revision 2: purpose exploration as the grill's sibling

The partner's review of the PR text found four places where it fell short of
the intent it encodes:

1. The third bullet sourced constraints only from "real-world context outside
   the codebase"; the intent also derives them from the higher purpose — and
   that higher purpose itself has to be discovered and given its nuances
   before anything is derived from it.
2. "The labor of defining the problem is yours, not theirs" read as relieving
   the partner of thinking. The exploration is carved between both sides; the
   agent drives it and, above all, interviews the partner for what only they
   hold.
3. "Clarity" is the wrong measure. A purpose can look clear and be narrow.
   Where the grill resolves what an initiative already poses, this process
   reaches past what seems settled into what the initiative should even be —
   which makes it a sibling of the grill, not a part of it.
4. What the design reaches for is the best possible manifestation of the
   initiative's intent and the higher purpose it serves, articulated downward
   into a system of goals and conditions rich enough that one result is right
   and the generic ones are wrong.

Change: the purpose material moved out of "The grill" into a new section,
"Exploring the purpose", placed before it, with a new path step 2 (later
steps renumbered; the composite-child skip becomes step 8). The done-criterion
now reads "the purpose and the system of goals and conditions under it".
A first draft kept three questions with the higher purpose folded into
"what precisely it is for"; after the first-round read below showed the
higher purpose asked in only about half the reps on both arms, it became
its own list item (four questions).

Snapshots:

- Before (PR head `68d6af5a`): `c586c072a953b4e42ba752f4e4012e3f988e2c66107cfe1d2143ffe5f1a21c1d`
- Three-question sibling: `1467a931e095b8ba77aacb2099e9a57c3d47608f04ec3d1e3cda315f97b58a8d`
- Four-question sibling (final, 2,800 words): `4eccc5fb8369e4b59e0677a8cd22ad5380e592704f997cb605b87a8e731de204`

Method as above, with two differences. Children ran with an empty temp
directory as cwd, so no project CLAUDE.md or auto-memory index loaded; they
still load the user-level CLAUDE.md, which carries a compact form of the
same principle — equal across arms, and it makes the before arm stronger
than a bare skill would be. `max_turns` was raised from 1 to 4 after 17 of
the 50 first-wave runs died at the one-turn cap (a structured-output or tool
attempt before the answer); only those 17 were re-run.

Rubric additions, read manually as before:

- *higher* — asks what higher purpose the initiative serves (what it is in
  service of), as distinct from which pain it removes.
- *reframe* — questions or proposes what the intent should be (an alternative
  lever or framing), rather than only clarifying the given one.

**First-round scenario** (same brief):

| Arm | Model | best | must-not | propose | higher | reframe |
|---|---|---:|---:|---:|---:|---:|
| Before | sonnet | 5/5 | 5/5 | 5/5 | 3/5 | 0/5 |
| Three-question | sonnet | 5/5 | 5/5 | 5/5 | 2/5 | 1/5 |
| Four-question | sonnet | 5/5 | 5/5 | 5/5 | 5/5 | 0/5 |
| Before | opus | 5/5 | 5/5 | 5/5 | 4/5 | 5/5 |
| Three-question | opus | 5/5 | 5/5 | 5/5 | 2/5 | 5/5 |
| Four-question | opus | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |

Notes from reading:

- The three original items held at 5/5 through the restructure on both
  models: moving the material into its own section and step displaced
  nothing.
- *higher* bound only when it got its own list item. Folded into "what
  precisely it is for", both models read that item as "which pain is this
  removing" (a failure-mode menu) and asked about the purpose above it in
  roughly half the reps — the same rate as the before arm. With its own item
  every rep asks it, in the skill's own words ("what is this in service
  of?", "what project or way of working is this in service of").
- *reframe* is model-bound and unmoved by this change: opus voices the
  alternative-lever challenge in every arm (the existing "framing is a
  starting point" paragraph), sonnet in none.
- The "put concrete things in front of them" sentence shows in the final
  arm more than before: two of five opus reps author a candidate scene of
  the best manifestation and ask the partner to correct it ("react to
  mine: I open a session on a repo I haven't touched in two months…"), one
  offers three architectures with "don't pick — tell me what's wrong with
  each", and one sonnet rep proposes the whole purpose reading — higher
  purpose, intent, best manifestation, must-not — for the partner to
  react to and correct.

**Shallow-purpose stopping scenario** (new). Same set-up as the earlier
stopping scenario, except round one *did* ask the three purpose questions
and got one line each ("making my sessions smarter over time"; "I stop
re-explaining my preferences and past decisions"; "must not be noisy or
slow"), then rounds two and three settled every decision. Classify DONE or
CONTINUE. Five reps per arm, both models.

| Arm | sonnet | opus |
|---|---|---|
| Before | 5 CONTINUE | 5 CONTINUE |
| Three-question | 5 CONTINUE | 5 CONTINUE |
| Four-question | 5 CONTINUE | 5 CONTINUE |

Not discriminating: the PR-head text already carried "stays open as the
decisions below reveal more of it", and every arm treats three one-line
answers as an unexplored purpose. What moved is the reason given. Before-arm
reasons quote the old tree metaphor ("a tree grown from a vague purpose").
Four-question reasons apply the new criteria as tests: "the higher purpose
was never asked about at all" (three of ten), "a generic answer would
satisfy every stated constraint, which is the tell the exploration is
unfinished" (two opus reps — the system-of-conditions criterion), "terse
clarity is easy to mistake for explored territory" (sonnet), and "the
purpose and the system of goals under it" as the stopping condition by
name.

**Thin-purpose stopping scenario** (from the first revision), four-question
snapshot, sonnet: 0 DONE / 5 CONTINUE, all five anchored on the sibling
purpose exploration by name and its four questions.

**Regression.** Authorized-technical PROCEED scenario: 5 proceed / 0 pause
on both sibling snapshots.

Limits: as above. The first-round scenario cannot show the co-carving or
the system-of-conditions emphasis directly; those show only in what the
stopping reps cite. Nothing here measures whether a full session's design
comes out more specific.
