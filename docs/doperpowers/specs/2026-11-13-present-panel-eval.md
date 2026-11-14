# The present rule: its replay over real turns

The evaluation behind acceptance 15 of
`docs/doperpowers/specs/2026-11-13-present-panel-design.md`: does the rule
that tells a session when to put something on its panel
(`mcp__to-human__present`) send it there where a panel is warranted, and
leave routine reports as text? The harness is
`tests/output-styles/to-human-present-eval.py`; its logic is tested by
`tests/output-styles/test-present-eval.py`, with no model call.

## Method

- **The turns.** Twenty points in the owner's transcripts
  (`~/.claude/projects/*/*.jsonl`, 2026-10-22 to 11-14) where a session under
  the `to-human` style wrote to its human: ten whose content warrants a panel
  by the rule's own terms and ten routine ones, listed below with why each is
  in its class. They were found by scanning 3,934 such points in 185
  sessions for the shapes of each kind (a message beside an ask with
  options, "approve" near "design", a session's third or later long message
  on the same findings, a short reply, a merge), then read one by one.
- **The context.** Claude Code records every request it sends in the
  session's transcript (`api-request` rows, delta-encoded over the
  conversation's own rows; `tests/output-styles/wire_replay.py`), so each
  turn is the exact request that produced the message: the system prompt,
  the tools, every message up to that point, the model, the effort and the
  thinking settings. Three things are changed: the output style in it is
  replaced by the arm's style; the arm's line is put at the end of the
  Reporting section of every copy of the owner's `~/.claude/CLAUDE.md` it
  holds (the copy as it stood that day); and `mcp__to-human__present` is
  offered beside the message tool, as `present.tsx` defines it.
- **A run.** The model writes the response again, on the turn's own model
  and effort, and goes on until it reaches the human: a run ends at the
  first response that calls the message tool, `present` or an ask tool, or
  that calls nothing; any other call (a command, a read) is answered as not
  run, for at most four responses. A `present` call is not answered, so no
  fork is spawned. A run counts when any of its responses calls `present`.
  Three runs per turn under the rule, one under the control.
- **Why a run goes on past a check.** With one response per run (the first
  round), 28 of 30 warranted runs and 12 of 30 routine ones made a command
  or read call and stopped there, so they never came to the choice the rule
  governs; the original requests sent again unchanged did the same in 3 of
  5 runs, so it is the models' habit before a report, not an artifact of the
  replay. Offered only the tools that reach the human, they called the
  command tool anyway (3 of 3).
- **What going on past a check costs.** The answer to an unrun call
  (`NOT_RUN`) tells the model it is in a replay of the session and its
  command did not run. A report written after that can talk to the human
  about the replay or the unrun command, or carry a degraded-work notice it
  would not otherwise; such a run is contaminated, and the runs that went
  past step 1 were read for it (listed under the counts). The answer can
  also change the report's channel: told it cannot check, a model may put
  less on a page it cannot verify. Each arm's runs are therefore shown by
  the step they reached the human at, step 1 being the uncontaminated
  replay of the original response.
- **The bar.** Of 30 runs over the routine turns at most 3 call the tool;
  of 30 over the warranted turns at least 21.

## The turns

| Turn | Class | Kind | Model, effort | Why it is in its class |
|---|---|---|---|---|
| w1 | warranted | decision | opus-5-5 xhigh | Asks what to do with the 49 unmerged worktrees left (35 GB), in two kinds with counts and sizes, after a cleanup that went wider than approved (Korean) (session `72609148`, 2026-11-04, 135k tokens) |
| w2 | warranted | decision | fable-5-2 xhigh | Recommends a full-length test over its own earlier default of a front part, with a table of the two options' cost, time and viewing; the choice goes to the ask dialog (Korean) (session `4d4a4036`, 2026-11-14, 244k tokens) |
| w3 | warranted | decision | opus-5-5 xhigh | All three memory designs fail the leak gate (a table of three measures by three designs); recommends a redesign and asks which way to go (session `c27e9d9d`, 2026-10-28, 195k tokens) |
| w4 | warranted | decision | opus-5-5 xhigh | Explains ticket #124 (redaction inside installed code) and puts build or defer to the human, with a recommendation (session `639ca648`, 2026-10-22, 288k tokens) |
| w5 | warranted | design | opus-5-5 xhigh | Presents the session-manager design (skill, subscriptions, briefing, two new sminos commands) and asks for approval before writing the spec (session `f89d7fb0`, 2026-11-01, 131k tokens) |
| w6 | warranted | design | opus-5-5 xhigh | Presents the full design of an OpenRouter models window with one open question, asking for approval or changes (session `95341a27`, 2026-10-27, 175k tokens) |
| w7 | warranted | design | opus-5-5 xhigh | Presents ticket #137's design (checking a saved page with the server before reuse) with the measurements behind it, for a ruling (session `700c5e84`, 2026-10-26, 143k tokens) |
| w8 | warranted | revision | fable-5-2 xhigh | The fourth correction in a session assembling a large UX spec: a card and a drawn frame the human answered rest on a wrong fact, so a rule changes and a question goes out (session `10d85d03`, 2026-11-12, 220k tokens) |
| w9 | warranted | revision | opus-5-5 xhigh | The third version of the list of what the human's note reorganization lost (18 places, then four kinds, now five more); asks again (Korean) (session `8e7e77ec`, 2026-11-01, 332k tokens) |
| w10 | warranted | revision | opus-5-5 xhigh | The third message on the whole-video judge's scene limit: the limit it reported, and had a fix designed around, was wrong (session `49104986`, 2026-11-04, 144k tokens) |
| r1 | routine | merge | opus-5-5 high | A PR merged after two CI fixes; installing the update is the human's (session `7a79acf5`, 2026-11-12, 128k tokens) |
| r2 | routine | merge | opus-5-5 xhigh | Both PRs of the work are merged and installed; the open items are listed (session `1cdcc7bc`, 2026-10-28, 210k tokens) |
| r3 | routine | merge | fable-5-2 high | One landing of a wave is on master; what is next in line (session `10d85d03`, 2026-11-14, 284k tokens) |
| r4 | routine | green run | fable-5-2 xhigh | Test rows passed on the final build and the VM is staged; nothing is needed (session `b4948247`, 2026-11-11, 213k tokens) |
| r5 | routine | merge | opus-5-5 xhigh | The first part of a milestone is merged; what comes next (session `49104986`, 2026-11-04, 176k tokens) |
| r6 | routine | problem resolved | fable-5-2 xhigh | Two stale entries in the view were one leftover wait loop; stopped, nothing lost (session `9ea1d75c`, 2026-11-13, 81k tokens) |
| r7 | routine | problem resolved | opus-5-5 high | A video is unlisted as asked, the live site checked, and how it comes back (session `904e094e`, 2026-11-08, 162k tokens) |
| r8 | routine | short answer | fable-5-2 high | Two models removed from the routing guide as asked; one value left to the human (Korean) (session `aad801e3`, 2026-11-11, 81k tokens) |
| r9 | routine | short answer | opus-5-5 xhigh | One sentence: the names stay as chosen and nothing changed (session `d1d2d6b0`, 2026-10-29, 98k tokens) |
| r10 | routine | short answer | opus-5-5 xhigh | Confirms that nothing behavioral changed; one documentation commit (session `40776d16`, 2026-10-31, 239k tokens) |

## Wordings and counts

One wording was run: the rule as `output-styles/to-human.md` holds it
(the paragraph that opens "Where `mcp__to-human__present` is among your
tools"), with the same sentence in the owner's CLAUDE.md copy in the first
person. The control is the style as it stood before the rule (HEAD of
`main`), with no CLAUDE.md line and `present` still offered. The rule arm
ran three runs per turn; the control, one.

> **Contamination is more than a few runs.** 7 of the rule's 60 runs and
> 2 of the control's 20 talk to the human about the replay or the command
> that did not run, and one more in each arm is borderline (listed below).
> They are counted in the tables as they came; none of them changes a
> class's verdict, since only one of them (w6, rule, run 3) calls
> `present`.

### Per class

| Arm | Class | Runs | Call `present` | Reached the human at step 1 / 2 / 3 / 4 | Never |
|---|---|---|---|---|---|
| rule | warranted | 30 | **8** | 3 / 21 / 6 / 0 | 0 |
| rule | routine | 30 | **0** | 24 / 3 / 2 / 1 | 0 |
| control | warranted | 10 | 0 | 2 / 6 / 2 / 0 | 0 |
| control | routine | 10 | 0 | 6 / 2 / 2 / 0 | 0 |

Under the rule, seven of the eight `present` calls came at step 2 and one
at step 1 (w6). The bar is at most 3 of 30 routine and at least 21 of 30
warranted: the routine side meets it, the warranted side does not (8).

### Per turn

Each run is shown by where it reached the human (P `present`, a an ask
dialog, m the message tool, t text with no call) and the step it did so
at.

| Turn | Kind | Rule (3 runs) | Control (1 run) |
|---|---|---|---|
| w1 | decision | a2 a2 a2 | a1 |
| w2 | decision (fable) | a2 a2 a2 | a2 |
| w3 | decision | **P2** a2 a2 | a2 |
| w4 | decision | a1 a2 a1 | a1 |
| w5 | design | **P2 P2** m2 | m2 |
| w6 | design | **P2 P1 P2** | a2 |
| w7 | design | **P2 P2** a3 | a2 |
| w8 | revision (fable) | m3 m2 a3 | a3 |
| w9 | revision | a2 a2 a2 | a2 |
| w10 | revision | m3 m3 m3 | m3 |
| r1 | merge | m1 m1 m1 | m2 |
| r2 | merge | m1 m1 m1 | m1 |
| r3 | merge (fable) | t3 t4 t2 | t3 |
| r4 | green run (fable) | m2 m2 m3 | m3 |
| r5 | merge | m1 m1 m1 | m1 |
| r6 | problem resolved (fable) | m1 m1 m1 | m1 |
| r7 | problem resolved | m1 m1 m1 | t2 |
| r8 | short answer (fable) | m1 m1 m1 | m1 |
| r9 | short answer | m1 m1 m1 | m1 |
| r10 | short answer | m1 m1 m1 | m1 |

By kind under the rule: designs 7 of 9, decisions 1 of 12 (11 went to the
ask dialog), revisions 0 of 9 (five message, four ask dialog). By model:
opus turns 8 of 24 warranted runs, fable turns (w2, w8) 0 of 6.

### Contaminated runs

A run past step 1 whose report to the human talks about the replay or the
unrun command. Every run that went past step 1 was read.

| Arm | Turn, run | What the report says |
|---|---|---|
| rule | w6, 3 (`present`) | a Critical notice: "I couldn't measure how fast ... loads", the measurement being the command that did not run |
| rule | r3, 1 | "The last two log appends did not execute (the shell answered 'Not run: this step is a replay of the session')" |
| rule | r3, 2 | "Shell commands are not running in this step: three calls in a row ... came back 'Not run'" |
| rule | r3, 3 | "My last log append for that status did not run, so that entry is not yet in the state log" |
| rule | r4, 2 | a Critical notice: "My last shell command was not executed: the tool answered that this step is a replay" |
| rule | r4, 3 | a Critical notice: "My last two shell commands were not run: the harness answered that this step is a replay" |
| rule | w8, 1 | "My shell commands stopped being executed after 14:10Z: the tool answered twice that the step is a replay" |
| rule (borderline) | w8, 2 | "history read from a transcript file (that check did not run)", one clause in a list of what is unchecked |
| control | r3, 1 | "the shell refused the command twice with 'not run: this step is a replay of the session'" |
| control | r4, 1 | a Critical notice: "My last two shell commands were not executed: the harness answered 'this step is a replay'" |
| control (borderline) | w6, 1 | "My last read didn't run", in its Not-verified list |

The fable sessions (r3, r4, w8) account for all but one of the clear
cases: they name the replay to the human; the opus sessions, told the same,
mostly go on without mentioning it.

### What it cost

Measured from the gateway's request log (rows with user agent
`Anthropic/Python`, 2026-11-14 07:56Z to 08:55Z: both replay rounds, the
first round, and the diagnostics):

| Model | Status | Requests | Input | Cache read | Cache write | Output |
|---|---|---|---|---|---|---|
| opus-5-5 | 200 | 186 | 186,558 | 22,127,727 | 5,307,833 | 523,628 |
| opus-5-5 | 400 | 3 | | | | |
| fable-5-2 | 200 | 70 | 123,754 | 9,227,668 | 3,013,786 | 252,341 |
| fable-5-2 | 429 | 75 | | | | |

The three 400s are the tools-restricted diagnostic (a `tool_reference` to
a tool the request no longer offered). The 75 fable 429s came when the
plan ran out at 08:30Z; most of them were the SDK's own retries
(`max_retries` 4) before the harness turned them off. A run averages 1.7
requests, each re-reading the turn's whole context (81k to 332k tokens)
from the cache.

## Reading the runs

- **The rule is what puts anything on the panel.** Offered `present`
  with its own description and no rule, no run in 20 called it; under
  the rule, 8 of 30 warranted runs did and no routine one. The routine
  side holds cleanly: every routine run under the rule reached the human
  through the message tool or as text, mostly at step 1, the original
  response's own point.
- **Designs go to the panel; decisions go to the ask dialog.** Seven of
  the nine design runs called `present`. Eleven of the twelve decision
  runs put their options in the ask dialog and no page beside it, as the
  original sessions did; the control's decision runs did the same. The
  rule names "a decision with its options" as panel content, but a model
  holding an ask tool reads the dialog as the place a decision with
  options already goes, and nothing in the rule says the page goes beside
  the dialog rather than in place of it.
- **Revisions never reached the panel.** None of the nine revision runs
  called `present`. These turns are a correction or a third version
  delivered in one message; read alone, the message does not look like
  "findings that keep being revised", which only the conversation behind
  it shows. A model judging the message in front of it, not the history,
  does not see the shape the rule names.
- **Fable turns are thin here.** Only w2 and w8 of the warranted turns
  ran on fable, a decision and a revision, the two kinds that failed on
  every model; 0 of 6 says nothing about fable's reading of designs.
- **The measurement's own limits.** 27 of 30 warranted rule runs reached
  the human only after a check was answered as not run, so the warranted
  counts are mostly of reports written after being told the session is a
  replay. Step 1 alone (3 warranted runs, 1 `present`) is too few to
  judge. The contaminated runs are listed above; removing the clear
  cases leaves 7 of 28 warranted and 0 of 25 routine, the same verdict.
- **Not run.** No rewording round: acceptance 15 is not declared here,
  and the next wording, if any, is the owner's call. The two gaps the
  counts point at are the decision with an ask dialog (the page beside
  the dialog) and the revision across turns (the session's own history
  as the signal).

### The decision turns' runs

What each run of a decision turn sent the human at the step it reached
them: the ask dialog (every one was a single question; the number is its
options), the message beside it, and whether it called `present`.

| Turn | Run | Ask dialog | Message beside it | `present` |
|---|---|---|---|---|
| w1 | rule 1 | 1 question, 3 options | none | no |
| w1 | rule 2 | 1 question, 3 options | none | no |
| w1 | rule 3 | 1 question, 3 options | none | no |
| w1 | control | 1 question, 3 options | none | no |
| w2 | rule 1 | 1 question, 3 options | none | no |
| w2 | rule 2 | 1 question, 2 options | yes, 1,672 characters: headings, a list, bold; no table | no |
| w2 | rule 3 | 1 question, 3 options | yes, 1,105 characters: headings, a list, bold; no table | no |
| w2 | control | 1 question, 3 options | none | no |
| w3 | rule 1 | 1 question, 3 options | none | **yes**, beside the dialog |
| w3 | rule 2 | 1 question, 3 options | yes, 2,799 characters: a table, a list, bold | no |
| w3 | rule 3 | 1 question, 3 options | none | no |
| w3 | control | 1 question, 3 options | yes, 2,689 characters: a list, bold; no table | no |
| w4 | rule 1 | 1 question, 4 options | yes, 2,071 characters: a table, a list, bold | no |
| w4 | rule 2 | 1 question, 4 options | yes, 2,724 characters: a list, bold; no table | no |
| w4 | rule 3 | 1 question, 4 options | yes, 2,249 characters: a list, bold; no table | no |
| w4 | control | 1 question, 3 options | yes, 2,438 characters: a list, bold; no table | no |

Where there is no message, the dialog carries the whole report: its
question runs 94 to 283 characters, and each option has a description of
28 to 307 characters.
