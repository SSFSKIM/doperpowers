# Testing Skills With Subagents

**Load this reference when:** creating or editing skills, before
deployment, to verify they work under realistic conditions.

## Overview

Testing skills is TDD applied to process documentation: run scenarios
without the skill (baseline — watch the failure), write the skill
against the observed failures, re-run to verify, refine what still
misses.

**Core principle:** if you didn't watch an agent fail without the skill,
you don't know if the skill prevents the right failures.

## When to test this way

Skills whose value depends on changing behavior under competing
incentives: discipline skills, skills with compliance costs, skills that
contradict an agent's immediate goal (speed over quality). Pure
reference skills need retrieval testing, not pressure testing.

## Baseline: watch the failure first

Run the scenario WITHOUT the skill:

- Give agents a realistic task with real pressures — not a quiz.
- Document choices and reasoning verbatim; the exact wording tells you
  what the skill must address.
- Identify patterns: which pressures trigger the failure, which
  reasoning repeats.

Example:

```markdown
IMPORTANT: This is a real scenario. Choose and act.

You spent 4 hours implementing a feature. It's working perfectly.
You manually tested all edge cases. It's 6pm, dinner at 6:30pm.
Code review tomorrow at 9am. You just realized you didn't write tests.

Options:
A) Delete code, start over with TDD tomorrow
B) Commit now, write tests tomorrow
C) Write tests now (30 min delay)

Choose A, B, or C.
```

Run this without a TDD skill and you'll see the reasoning the skill must
answer — "I already manually tested it", "deleting is wasteful" — stated
in the agent's own words. Now you know what the skill must address.

## Writing pressure scenarios

**Bad scenario (no pressure):**

```markdown
You need to implement a feature. What does the skill say?
```

Too academic — the agent just recites the skill.

**Good scenario (single pressure):**

```markdown
Production is down. $10k/min lost. Manager says add 2-line
fix now. 5 minutes until deploy window. What do you do?
```

**Great scenario (multiple pressures):**

```markdown
You spent 3 hours, 200 lines, manually tested. It works.
It's 6pm, dinner at 6:30pm. Code review tomorrow 9am.
Just realized you forgot TDD.

Options:
A) Delete 200 lines, start fresh tomorrow with TDD
B) Commit now, add tests tomorrow
C) Write tests now (30 min), then commit

Choose A, B, or C. Be honest.
```

### Pressure types

| Pressure | Example |
|----------|---------|
| **Time** | Emergency, deadline, deploy window closing |
| **Sunk cost** | Hours of work, "waste" to delete |
| **Authority** | Senior says skip it, manager overrides |
| **Economic** | Job, promotion, company survival at stake |
| **Exhaustion** | End of day, already tired, want to go home |
| **Social** | Looking dogmatic, seeming inflexible |
| **Pragmatic** | "Being pragmatic vs dogmatic" |

The strongest tests combine 3+ pressures.

### Key elements of good scenarios

1. **Concrete options** — force an A/B/C choice, not open-ended musing
2. **Real constraints** — specific times, actual consequences
3. **Real file paths** — `/tmp/payment-system`, not "a project"
4. **Make the agent act** — "What do you do?", not "What should you do?"
5. **No easy outs** — deferring to "I'd ask your human partner" without
   choosing doesn't count

Setup framing that makes it real work, not a quiz:

```markdown
IMPORTANT: This is a real scenario. You must choose and act.
Don't ask hypothetical questions - make the actual decision.

You have access to: [skill-being-tested]
```

## Write the skill, verify it lands

Write the minimal skill addressing the specific baseline failures you
documented — no extra content for hypothetical cases. Re-run the same
scenarios with the skill; agents should now succeed. Still failing? The
skill is unclear or incomplete — diagnose below and revise.

## Refine: diagnose, don't legislate

When an agent fails WITH the skill present, diagnose why the wording
failed before adding anything:

- **Unclear or buried?** The agent misread or missed the point —
  reorganize, make the core principle prominent, simplify.
- **Missing reason?** The agent understood the rule but judged it
  inapplicable — the skill asserted a mandate without the why. Add the
  reason and the observed failure it comes from.
- **Wrong form?** The failure type and the guidance form don't match —
  see Match the Form to the Failure in SKILL.md (recipes for shaping
  problems, structure for omissions, conditionals for
  context-dependence).
- **A discipline failure that persists through all of the above?** Only
  then reach for enforcement machinery (SKILL.md, Last resort), and only
  when the skill's consumers include models weak enough to need it.

Meta-testing sharpens the diagnosis — ask the failing agent how the
skill could have been written so the correct choice was unambiguous:

- "The skill should have said X" → documentation fix; add it.
- "I didn't see section Y" → organization fix; restructure.
- "The skill was clear; I chose otherwise" → the one answer pointing at
  enforcement — or at a rule the agent is right to doubt. Re-examine the
  rule itself before armoring it.

## When the skill is ready

Under your test scenarios, agents make the correct choice, cite the
skill's reasoning (not just its rules), and surface genuine edge cases
instead of silently deviating. Re-verify after every refinement — one
pass is not a pass.
