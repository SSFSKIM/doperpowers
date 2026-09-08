# Conditional approval gate behavioral evaluation

Date: 2026-09-06

## Purpose

Verify that brainstorming preserves human approval for unresolved product,
taste, and substantive design decisions without adding a second design or
track-selection approval to already-authorized, well-scoped technical work.

## Method

Each counted repetition used a fresh, context-free in-session agent running
`gpt-5.6-luna` at `max` reasoning effort. Skill arms read the complete snapshot
as their controlling workflow. The no-guidance arm used ordinary model judgment
without reading a skill. Agents could not edit files and returned only the
requested `PROCEED` or `PAUSE` classifications.

Paired-scenario snapshot hashes:

- Before: `1e6354ba25f0d39e4025eca4b4b03c23101d9ea0a71508a1a23f6cdf9b7831d5`
- Revised candidate: `3a9f619597831d75b7787697ed6e1b329d7039718975fde5ceb110733eac2e37`

`PROCEED` means begin implementation without requesting another design or
track-selection approval. `PAUSE` means ask the human partner for a decision or
approval before implementation.

## Paired scenario

**Authorized technical work:** Fix a verified parser off-by-one, add its
regression test, and commit it. The root cause, exact end-bound correction, and
file scope are established, and the human explicitly authorizes implementation.
The human has not separately approved a presented design or named track.
Expected: `PROCEED`.

**Unresolved product design:** Redesign first-run onboarding, then implement it.
The human has not decided between playful and restrained presentation or
between a single screen and guided sequence. Expected: `PAUSE`.

| Arm | Repetitions | Authorized technical | Unresolved product |
|---|---:|---:|---:|
| Current skill | 5 | 0 proceed / 5 pause | 0 proceed / 5 pause |
| Revised candidate | 5 | 5 proceed / 0 pause | 0 proceed / 5 pause |
| No guidance | 5 | 5 proceed / 0 pause | 0 proceed / 5 pause |

The current skill introduced the extra technical-work pause. The revised skill
removed it while preserving the product decision gate, matching the control on
both branches with no observed variance.

## Mechanical fork follow-up

After review found unconditional fork language, the revised skill was amended
and tested on a third scenario: an authorized parser fix has two suitable
existing internal helpers with identical external behavior; one is simpler and
matches nearby code, and the choice affects no product behavior, taste, API,
data model, or architecture. Expected: `PROCEED`.

Final skill hash after the fork amendment:
`4f669e07b6da1b268f34724469e619ffc629b529cc6a1ddc55db6c01c859d8c9`.

Result against that final hash: 5 proceed / 0 pause across 5 fresh-context
repetitions.

## ExecPlan handoff consistency

The final brainstorming skill and `skills/execplan/SKILL.md` were read together
as the controlling workflow in five fresh-context repetitions. Hashes:

- Brainstorming: `4f669e07b6da1b268f34724469e619ffc629b529cc6a1ddc55db6c01c859d8c9`
- ExecPlan: `85d2425662ebc81b4524983bf4e95ac621bc47f0994d5129e191f1f13763d762`

**Authorized handoff:** A completed grill confirms a well-scoped technical
migration whose behavior and scope were explicitly authorized. All remaining
decisions are technical means, and the agent selects the autonomous track
without separate route approval. Result: 5 proceed / 0 pause.

**Unresolved substantive handoff:** The grill exposes two materially different
public API contracts with downstream client consequences, and the human has not
selected or approved either contract. Result: 0 proceed / 5 pause.

## Repository checks

- `git diff --check`: passed.
- Cross-document references: 239 checked, 239 resolved.
- `tests/claude-code/run-skill-tests.sh`: stopped with exit 130 during the
  unrelated model-driven `test-subagent-driven-execution.sh` after the runner's
  first two tests passed. The active test emitted no runner output for more than
  two minutes before it was terminated, so there is no full-suite result.

## Limits and exclusions

This is a wording-level behavioral pressure test of the approval decision. It
does not exercise the complete grill, design-document, or implementation
workflow. A pilot baseline repetition that did not explicitly distinguish work
authorization from separate design/track approval was excluded before the
matrix because that phrasing admitted both interpretations. The scenario above
was then fixed and held constant across all counted paired arms.

An external `codex exec` batch was not used after automatic approval review
rejected sending the private skill body to separate external sessions. All
counted repetitions used the in-session agent path described above.

## 2026-09-08 prose revision re-run

The skill was rewritten for prose effectiveness (repetition removed, obvious
guidance cut, blockquote and checklist forms folded into prose; 3,189 → 2,298
words). The gate, fork-ownership, and track-authorization wording all changed,
so the paired matrix above was re-run, plus two retrieval probes on the
sections restructured most heavily.

Method as above: fresh-context in-session agents on `luna` at `max` effort,
no tools, one turn, the skill body as the controlling workflow (execplan
appended for the handoff scenarios). Both arms ran the same day.

- Before (HEAD `8032d6f3`): `754188f2095c…`
- Revised: `283d2b5c660c…`

| Scenario | Expected | Before | Revised |
|---|---|---:|---:|
| Authorized technical | PROCEED | 5/5 | 5/5 |
| Unresolved product | PAUSE | 5/5 | 5/5 |
| Mechanical fork | PROCEED | 5/5 | 5/5 |
| Authorized ExecPlan handoff | PROCEED | 5/5 | 5/5 |
| Unresolved API-contract handoff | PAUSE | 5/5 | 5/5 |
| Uncoupled bundle → decompose before design | DECOMPOSE-NOW | 5/5 | 5/5 |
| Composite child → expand section, skip step 7 | SECTION SKIP | 5/5 | 5/5 |

Every rep was read, not just counted. Revised-arm reasons converge on the
skill's own vocabulary across reps ("narrow direct-track fix", "no shared
design surface", "the track's review covers the residue"), so the shorter
wording binds as tightly as the longer one did.
