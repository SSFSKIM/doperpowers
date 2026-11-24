# C1: Behaviour baseline of the question sheet — ledger

> **Parent:** composite spec `docs/doperpowers/specs/2026-11-23-question-sheet-design.md` in the MAWS repository, child **C1** ("Behaviour baseline"). **Parent pin:** `ad4427f93`. **Ticket:** MAWS board #866. The child's section in that document is its spec; this file carries the dispatch brief, then the record of the run.

## Brief

**Read first:** the whole spec; the section is "### C1: Behaviour baseline". §2.1 is the tool input a stub must accept, §2.2 its result, §2.4 the three things the tool's description asks of the agent, §10 the open point on capturing context, §12 the two evals E1 and E2.

**Why this exists.** The design replaces a question tool because agents ask a second question instead of changing the first, and ask questions a human cannot judge without the transcript. No mechanism fixes either; only the agent's behaviour under the new tool's description does. These evals decide whether the design works and what its description must say, so a harness that can be passed without the behaviour is worse than none: E2's judge must see only the card (the question's fields as a surface would show them), never the session, and both evals must run on long sessions where the temptation actually arises (an agent that has moved on from the moment it asked).

**What to build.** In a worktree: `git -C /Users/new/Developer/GitHub/doperpowers worktree add .claude/worktrees/question-sheet-c1 -b question-sheet-c1 origin/main`. Follow the existing behaviour evals under `tests/output-styles/` for form, runner and how they call a model. Write a stub of the tool (accepts §2.1's input, returns §2.2's result, records calls; no sheet, no delivery beyond what the scenarios need), a first wording of the tool's description from §2.4, the two evals each runnable from one command, and a ledger at `docs/doperpowers/ledgers/2026-11-23-question-sheet-c1.md` that opens with the citation above and this brief, then your progress, decisions with their reasons, and surprises. Commit as you go.

**Stop before the paid baseline.** When the harness runs end to end on one or two cheap smoke cases, stop and report, before running the baseline: how many sessions each eval needs for a result worth trusting and why that many, which models at which effort for the subject and for the judge, and the estimated cost. The owner is told the size of any sizable model fan-out before it launches, so the baseline waits for the reply. Do not open a pull request yet.

**Not yours:** the real tool, the sheet's record, anything in `sminos/hooks/mods/`. Do not edit the composite spec; a statement in it that the work shows wrong goes in the report with the evidence.

## What exists

- `tests/output-styles/question_sheet.py`: the stub (`Sheet`: §2.1's validation as a whole, then each entry alone; ids `q<n>` never reused; revisions; the ownership rule; reference capture from the simulated project, `.env` refused; §2.2's result with entry places when part of a call was refused; every call recorded), the tool definition built from an arm file, the card (`render_card`, §8's card as text), the simulated project's tools, the run loop with prompt caching, and the judge call.
- `tests/output-styles/question_sheet_session.py`: the scripted sessions in the simulated project `tally` (`tests/output-styles/question-sheet/world/`), E1's and E2's triggers, E2's matters with their facts, and E2's calibration cards.
- `tests/output-styles/question-sheet/description-v1.md`: the first wording of the description (§2.4).
- `tests/output-styles/question-sheet-revise-eval.py` (E1) and `tests/output-styles/question-sheet-card-eval.py` (E2): one command each; their docstrings say what they run and how they score.
- `tests/output-styles/test-question-sheet-logic.py`: the offline test (no model call).

## Progress

- [x] (2026-11-23) Worktree and branch `question-sheet-c1` from origin/main b43da6bcd.
- [x] (2026-11-23) Probe of the gateway: a replayed tool loop with no thinking blocks is accepted, and prompt caching hits through it (38,454 tokens written, then read).
- [x] (2026-11-23) Stub, sessions, both evals and the offline test; the offline test passes.

## Decisions

## Surprises
