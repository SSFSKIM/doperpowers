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
- `tests/output-styles/question-sheet/description-v1.md`: the first wording of the description (§2.4). `description-v2-ask-early.md`: v1 with the one-call sentence replaced by "Put a question on the sheet as soon as you know you need it, not at the end of your turn: the human may be reading the sheet now. Questions you have at the same moment go in one call" (prepared, not run).
- `tests/output-styles/question-sheet-revise-eval.py` (E1) and `tests/output-styles/question-sheet-card-eval.py` (E2): one command each; their docstrings say what they run and how they score.
- `tests/output-styles/test-question-sheet-logic.py`: the offline test (no model call).

## Progress

- [x] (2026-11-23) Worktree and branch `question-sheet-c1` from origin/main b43da6bcd.
- [x] (2026-11-23) Probe of the gateway: a replayed tool loop with no thinking blocks is accepted, and prompt caching hits through it (38,454 tokens written, then read).
- [x] (2026-11-23) Stub, sessions, both evals and the offline test; the offline test passes.
- [x] (2026-11-23) Smoke, about $9 at list price over 14 subject runs and the judges. E2's judges calibrated 6 of 6 (each bare card fails, each full card passes). E1: option_gone short revised; on the far history option_gone revised (twice), premise revised, subagent revised, distinct added a new question (twice), no duplicate. E2: cap short, cap long, pii long and all long each put their questions in one call; every card about a scenario's matter passed on the long history (5 of 5), the far-back reasons included. The harness faults the smoke found are fixed (below).
- [x] (2026-11-23) The dispatcher's go, with the owner's sizing (about $140, both wordings, effort medium or low) and rulings: v2 is the wording under test (§2.4 at MAWS `be9a8b749`: ask when a question comes up, the whole frontier in one call, then keep working), v1 the comparison; the stub answers `Nothing done.` for a call in which nothing was done (§2.2, X7) and refuses a duplicate option label for its entry alone (§2.1). v2 reworded to that sentence; the stub updated, and a reference with no range taken whole (over 256 KB refused) per §2.3 at the same pin.
- [x] (2026-11-23) The baseline, $113.73 at list price (below).

## Decisions

- **Replay plus a live tail, not a live session from the start.** Each session is a scripted prefix (the human's task, the reading, the work) built through the same simulated tools the live part uses, then the model continues live from the scenario's trigger. A prefix written once makes the runs comparable and lets one cache serve every rep; a live start would cost a 60k-token session per run and put the scenario's facts wherever the model happened to look.
- **Long means about 62k tokens at the first live request** (about 90 messages, about 45 tool rounds), of which about 40 rounds of work sit between E1's ask and its trigger: M1 and M2 built and tested, a DST bug chased through the stdlib's `zoneinfo` and `_pydatetime`, `csv` and `_pydecimal` read, an independent review and its fixes, the full suite verbose and the branch's diff. The stdlib source is read from the running interpreter at run time (nothing third-party committed; the version is recorded with the results).
- **E1's distance is isolated.** `near` and `far` hold the same steps; only the ask's place moves (`far`: ask, then the work; `near`: the work, then the ask). far minus near is what having moved on costs, at equal length.
- **E2's facts are placed by design.** The reasons behind each matter are read at the session's start (the spec, `permissions.py`, `models.py`, `roles.py`, `schema.sql`); only the numbers arrive with the trigger. The rubric (`MATTERS`) marks each fact essential or not and where it was shown, and the summary reports fact presence by where.
- **E2's judges see only the card, and are calibrated.** The facts judge and the reader get `render_card`'s text and nothing of the session. `--calibrate` checks that hand-written bare cards fail and full cards pass; the first full tz card I wrote failed, rightly (an option without its consequence), and was fixed, not the judge.
- **The reader is the median of three.** One reader's verdict on the same card flipped between yes and partly across samples (smoke: the same cap card passed alone and failed with notes appended, the reasons near-identical). Three samples per counted card; one for a card outside the scenario's matters, which no pass rate counts.
- **Pass rates count only the scenario's matters.** A run raises other matters the world holds (the legacy writer's cron caller, the formula guard on phone numbers, a BOM for Excel, the other two matters); its card for a matter whose numbers it never saw cannot carry them, so those cards are reported by the reader alone.
- **A revision of E1's target counts as revised even when it broadens the question.** The same-decision judge called the subagent run's revision of q3 (from "accounts with no zone" to "which format every export uses") a different matter; that is the revision the scenario wants. The judgment decides only the distinct control (an open question repurposed for the new matter).
- **Runs end one response after the first sheet call, or at the turn's end, at most 20 responses.** 8 was too few: twice the agent noted the matter and kept working past it.
- **The canned shell is stateful, and a model answers what it cannot.** git status, diff, commit, log and reflog follow the files; heredocs, `sed -i`, `pytest -v/-k/-m`, staging queries for the session's numbers. A command it cannot answer goes to `claude-sonnet-5-5` at low effort with the files it names, the branch's history, its own earlier answers and the facts the session established, told to invent no problem; each answer is kept on the run.
- **Subject `claude-opus-5-5` at high effort**, as the to-human evals run; judges `claude-opus-5-5`, low for E1's same-decision judgment, medium for E2 (the effort it was calibrated at).
- **The stub's reading of two open points** (for C2, not decided here): an option-label clash refuses the whole call as a schema failure; a call whose every entry was refused returns only its `Not done:` line.

## Surprises

- **The agent asks at the end of its turn.** In every smoke run the first sheet call came in the turn's last response or two, after 2 to 17 responses of other work, often beside the final message; twice it wrote that it was "flagging" the cap and went on. With "put every question you have now in one call" and no blocking, it collects. A question known at the trigger reaches the human when the turn ends, which in a long unattended turn is much later. Both evals now record responses before the first sheet call; v2 is the wording to test against it.
- **The agent audits its environment.** Every fault of the simulated project surfaced in its notes or on its cards: a heredoc run as commands, `git status` clean after edits, a commit on the wrong base, a quoted `;` splitting a commit message, literal `\n` in two generated outputs, a scripted test using undefined fixtures and a total over the cap, a split `2>&1`, a simulator inventing tests. It stopped trusting its tools and sent a Critical message about them, and one card told the human to re-run the numbers because "the shell started returning wrong output". A harness for behaviour over long runs has to be consistent before it measures anything; each fault is fixed and the offline test checks it.
- **Cards are good.** On the long history the agent restated the far-back reasons (the cap's memory rationale, that viewers are contractors and auditors, that a column without a grant is open to every member) without being shown them again, and added considerations of its own (Excel's 1,048,576-row limit, what each option does to the browser view).
- **The gateway once answered "This account is out of plan usage until 2026-11-27T17:00:00Z"**, then served every model a minute later: an account behind it is exhausted, and a long fan-out may meet it again.

## Baseline (2026-11-23)

Subject `claude-opus-5-5` at **medium** effort (the owner's ruling); judges `claude-opus-5-5`, low for E1, medium for E2, as calibrated (6 of 6); shell simulator `claude-sonnet-5-5` at low. Results are kept under `~/.local/share/question-sheet-c1/baseline/`; `python3 tests/output-styles/question-sheet-report.py <files>` prints every figure below. No gateway refusal for plan usage occurred.

| rows | runs | subject | judges | simulator | total |
|---|---|---|---|---|---|
| E1 far, both wordings, 4 scenarios × 10 | 80 | $29.73 | $0.97 | $1.07 | $31.77 |
| E1 near, v2, 3 changed scenarios × 5 | 15 | $5.89 | $0.23 | $0.28 | $6.40 |
| E2 long, both wordings, 4 scenarios × 8 | 64 | $30.95 | $20.13 | $3.76 | $54.84 |
| E2 short, v2, 4 scenarios × 3 | 12 | $2.05 | $3.37 | $0.19 | $5.61 |
| E2 cap long on the fixed prefix, both × 8 | 16 | $5.13 | $4.24 | $0.20 | $9.57 |
| E1 far on the fixed prefix, both, option_gone and premise × 5 | 20 | $5.17 | $0.23 | $0.14 | $5.54 |
| **total** | 207 | $78.92 | $29.17 | $5.64 | **$113.73** |

The last two rows were added inside the budget after the first rows showed the agent auditing inconsistencies of my scripted prefix (below, "The environment"); they rerun the affected cells on the fixed prefix.

### E1: revise rather than ask again

| arm | history | option_gone | premise | subagent | distinct (control) |
|---|---|---|---|---|---|
| v1 | far | revised 10/10 | revised 10/10 | revised 10/10 | added 10/10 |
| v2 | far | revised 10/10 | revised 10/10 | revised 10/10 | added 10/10 |
| v2 | near | revised 5/5 | revised 5/5 | revised 5/5 | — |
| v1 | far, fixed prefix | revised 5/5 | revised 5/5 | — | — |
| v2 | far, fixed prefix | revised 5/5 | revised 5/5 | — | — |

No duplicate, no untouched target, no cut-off run, no repurposed question, and no schema error in 125 runs. On the far history, per wording: failures 0 of 30 (95% upper bound 11.4%), duplicates 0 of 30; the control 0 of 10 repurposed (upper 27.8%). Having moved on costs nothing measurable: near and far both revise every time.

**Responses before the first sheet call** (the trigger shows the change in the response before the first):

| arm | far (first prefix), median per scenario | fixed prefix, median | in the trigger's response or the next | first call at the turn's end |
|---|---|---|---|---|
| v1 | option_gone 9, premise 9, subagent 5, distinct 7.5 | option_gone 3, premise 4 | far 4/40; fixed 1/10 | far 37/40; fixed 5/10 |
| v2 | option_gone 9.5, premise 4.5, subagent 7.5, distinct 4.5 | option_gone 2, premise 9 | far 2/40; fixed 1/10 | far 29/40; fixed 3/10 |

**What asking early did.** It did not change revise-versus-duplicate: both wordings revised every time. It did not make the agent ask sooner after the trigger: in every run, of either wording, the trigger's own response says the question changed ("The download layer only allows one file per job ... so I'm revising q1"), and then the agent checks something first: who still calls the legacy writer (and then asks that too, in the same call: the frontier batched), whether the suite passes on the rebased branch, or, on the first prefix, the inconsistencies it found in its own earlier work. What v2 changed is what follows the call: the agent kept working after it in 11 of 40 far runs, against 3 of 40 under v1 (Fisher's exact, one-sided, p ≈ 0.02). On the fixed prefix the wait shrinks to 2 to 4 responses for option_gone under both wordings; premise still runs the suite first (up to 13 responses).

### E2: a card judged alone

Counted cards are those about the scenario's own matters; the reader is the median of three readers; a card passes with every essential fact of its matter and the reader's yes.

| arm | history | cap | pii | tz | all (three matters) | total |
|---|---|---|---|---|---|---|
| v1 | long | 3/8 | 7/8 | 7/7 | 18/23 | **35/46** (76%; 95% lower 62%) |
| v2 | long | 3/8 | 7/8 | 8/8 | 16/23 | **34/47** (72%; 95% lower 58%) |
| v2 | short | 1/3 | 3/3 | 3/3 | 6/9 | 13/18 |
| v1 | long, fixed prefix | 2/8 | — | — | — | 2/8 |
| v2 | long, fixed prefix | 4/8 | — | — | — | 4/8 |

- Every run put its questions in one call (asking calls 1 per run in all 92 runs that asked); one v1 tz run asked nothing (matters asked 46/48 v1, 47/48 v2 on the long history). Runs asked about five other matters each on average (the legacy writer's cron caller, the formula guard on phone numbers, a BOM for Excel, the tzdata floor), with the reader's yes on 70% to 90% of those cards.
- **Facts by where they were shown**, long history, both wordings: the reasons read at the session's start were on the card every time (start 39/39 and 16/16 per arm in `all` and `pii`, 8/8 in `cap`, 14/14 and 16/16 in `tz`); the misses are trigger numbers (acme being the only account over the cap) and an option's consequence. Distance did not lose the far-back facts.
- **No reader gave a "no" to any counted card** (only the bare calibration cards get it). pii and tz are near the ceiling (yes on 29 of 31 and 30 of 32 counted cards per wording). cap is the outlier, and on the fixed prefix it is the reader alone: essential facts on 15 of 16 cap cards, reader yes on 7 of 16. The reader's "partly" on cap asks mostly for what the session never learned (the timeout of M3's job runner, which does not exist yet; production growth; whether the customer opens the file in Excel) and in part for what it did (the smoke's timings, the file size, the legacy writer's other caller). Choosing a new number is open-ended, and the reader's bar is above what any card could reach there.
- **The wording made no difference to the cards** (76% against 72%, within noise).

### Automatic capture of context (§10): recommendation, do not add it

Paired on the same counted cards, pass alone against pass with the agent's own words around the call appended:

| arm | rows | both | alone only | with capture only | neither | cards with no notes |
|---|---|---|---|---|---|---|
| v1 | long | 33 | 2 | 2 | 9 | 16 |
| v2 | long | 32 | 2 | 0 | 13 | 11 |
| v1 | cap, fixed prefix | 1 | 1 | 0 | 6 | 7 |
| v2 | cap, fixed prefix | 3 | 1 | 1 | 3 | 4 |
| v2 | short | 13 | 0 | 0 | 5 | 5 |

Capture turned 3 failing cards into passing ones and 6 passing ones into failing ones. The words it would capture are working notes (median 171 characters; none at all on 94 of 324 cards): what the agent checks next, and, on the first prefix, its doubts about the environment ("I can't trust the memory figure yet"), which a reader takes as doubt about the question. The cards already carry the far-back reasons capture would be meant to rescue (above). Capture would add noise to a card and supply nothing it lacks.

### Proposed thresholds for Acceptance 14

On the definitions above (C1's harness at its commit of this baseline; subject at the effort the shipped sessions run; judges at the calibrated efforts; `--calibrate` passing 6 of 6 before any run):

- **E1**, far history, 3 changed scenarios × 10 runs and the control × 10: at most 1 failure of 30 in the changed scenarios (a failure: duplicated, revised and duplicated, untouched, or cut off), and no repurposed question of 10 in the control. The baseline is 0 of 30 and 0 of 10 for both wordings; at a true failure rate of 15%, 30 runs show 2 or more failures 95% of the time.
- **E2**, long history, 4 scenarios × 8 runs (about 47 counted cards):
  1. every essential fact of its matter on at least 85% of counted cards (baseline 87% and 85%, 94% on the fixed prefix's cap);
  2. no reader "no" on more than 2 counted cards (baseline 0);
  3. at least 85% of the pii and tz cards pass (baseline 94% for both wordings).
  The cap matter's overall pass rate is reported and not gated until its reader is calibrated for an open-ended choice of a number: as it stands, a card with every fact passes half the time.
- **Timing** is reported and not gated: responses before the first sheet call, and whether the agent keeps working after it. The baseline shows no wording that makes the agent ask sooner after the trigger; v2 makes it keep working after asking.

### The environment

The first prefix had three inconsistencies the agent audited in most runs before acting: the branch's diff listed five of its twelve changed files, the full suite was 214 tests in one output and 99 in another, and my RSS fixture added a constant 71 MB to its measurement. Agents said so ("the branch diff is missing some of my commits", "the 88 MB figure is partly invented") and spent responses on it, which is what inflated the far rows' responses before the first sheet call (median 9 against 2 to 4 on the fixed prefix) and put "an unreliable session" on some cap cards. The far rows of both wordings ran on the same prefix, so their comparison stands; the fixed prefix (commit 88ddb5ba5) reran the affected cells. Also fixed on the way: a slow test that passed in 0.39 s on a missing fixture, a python heredoc that printed nothing, `git log -- path` ignoring its paths, and Claude Code's heredoc form of a commit message.

### Where the runs bear on the composite

- **§2.4's ruling rests on a smoke observation my environment caused.** "Told only to put every question in one call ... every agent held its questions to the last response or two of its turn": in the smoke the agent was fighting the simulated shell for most of each turn. On the fixed prefix, v1 asks 2 to 4 responses after the trigger and is mid-turn in half the runs; v2 asks no sooner. The ruling's wording is harmless (it performs as v1 does on every measure) and adds one thing: the agent keeps working after asking more often. The statement of the premise should say the wording did not change when the agent asks.
- **§12 E1 and observed problem 2**: with a revise in the tool and either wording, the agent revised in 125 of 125 runs and never asked a second question for the same decision. The problem did not reproduce; E1 guards against a regression rather than measuring a gap.
- **§10**: the runs answer its open point: agents do not leave `context` empty where the card needs it (far-back reasons present on every counted card), and capture would not help (above). Automatic capture can move from Deferred to Out of scope.
