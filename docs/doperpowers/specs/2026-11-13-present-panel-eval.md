# The present rule: its replay over real turns

The evaluation behind acceptance 15 of
`docs/doperpowers/specs/2026-11-13-present-panel-design.md`: does the rule
that tells a session when to put something on its panel
(`mcp__to-human__present`) send it there where a panel is warranted, and
leave routine reports as text? The harness is
`tests/output-styles/to-human-present-eval.py`; its logic is tested by
`tests/output-styles/test-present-eval.py`, with no model call.

**Result.** Two wordings were run. The second, after the human's ruling
that a decision gets a panel only when the ask dialog cannot carry it,
puts designs on the panel in 9 of 9 runs and the decision the dialog cannot
carry in 2 of 3. It keeps every one of the 36 text-side runs as text. It
never puts a revision on the panel (0 of 9). These counts are on
byte-exact rebuilds: the five turns whose replayed request had lacked text
the session read were run again. The bar is met on the text side and
missed on the warranted side, 11 of 21 against 15, on revisions alone.

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
  turn is the request that produced the message, rebuilt byte for byte
  where the rows allow: the system prompt, the tools, every message up to
  that point, the model, the effort and the thinking settings. In both
  rounds nine turns carried one or two messages the rebuild could not
  match and put in from the closest rows; what they were and how they bear
  on the counts is under "What the rebuild substituted". Three things are changed: the output style in it is
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
- **The bar.** First: of 30 runs over the routine turns at most 3 call
  the tool; of 30 over the warranted turns at least 21. After the human's
  ruling on decisions (below, "The relabelling"): of the 36 runs over the
  turns that stay text at most 3; of the 21 over the warranted turns at
  least 15.

## The turns

| Turn | Class (first, then after the ruling) | Kind | Model, effort | Why it is in its class |
|---|---|---|---|---|
| w1 | warranted, then text | decision; then one the dialog carries | opus-5-5 xhigh | Asks what to do with the 49 unmerged worktrees left (35 GB), in two kinds with counts and sizes, after a cleanup that went wider than approved (Korean) (session `72609148`, 2026-11-04, 135k tokens) |
| w2 | warranted, then borderline | decision | fable-5-2 xhigh | Recommends a full-length test over its own earlier default of a front part, with a table of the two options' cost, time and viewing; the choice goes to the ask dialog (Korean) (session `4d4a4036`, 2026-11-14, 244k tokens) |
| w3 | warranted | decision; then one the dialog cannot carry | opus-5-5 xhigh | All three memory designs fail the leak gate (a table of three measures by three designs); recommends a redesign and asks which way to go (session `c27e9d9d`, 2026-10-28, 195k tokens) |
| w4 | warranted, then text | decision; then one the dialog carries | opus-5-5 xhigh | Explains ticket #124 (redaction inside installed code) and puts build or defer to the human, with a recommendation (session `639ca648`, 2026-10-22, 288k tokens) |
| w5 | warranted | design | opus-5-5 xhigh | Presents the session-manager design (skill, subscriptions, briefing, two new sminos commands) and asks for approval before writing the spec (session `f89d7fb0`, 2026-11-01, 131k tokens) |
| w6 | warranted | design | opus-5-5 xhigh | Presents the full design of an OpenRouter models window with one open question, asking for approval or changes (session `95341a27`, 2026-10-27, 175k tokens) |
| w7 | warranted | design | opus-5-5 xhigh | Presents ticket #137's design (checking a saved page with the server before reuse) with the measurements behind it, for a ruling (session `700c5e84`, 2026-10-26, 143k tokens) |
| w8 | warranted | revision | fable-5-2 xhigh | The fourth correction in a session assembling a large UX spec: a card and a drawn frame the human answered rest on a wrong fact, so a rule changes and a question goes out (session `10d85d03`, 2026-11-12, 220k tokens) |
| w9 | warranted | revision | opus-5-5 xhigh | The third version of the list of what the human's note reorganization lost (18 places, then four kinds, now five more); asks again (Korean) (session `8e7e77ec`, 2026-11-01, 332k tokens) |
| w10 | warranted | revision | opus-5-5 xhigh | The third message on the whole-video judge's scene limit: the limit it reported, and had a fix designed around, was wrong (session `49104986`, 2026-11-04, 144k tokens) |
| r1 | routine, then text | merge | opus-5-5 high | A PR merged after two CI fixes; installing the update is the human's (session `7a79acf5`, 2026-11-12, 128k tokens) |
| r2 | routine, then text | merge | opus-5-5 xhigh | Both PRs of the work are merged and installed; the open items are listed (session `1cdcc7bc`, 2026-10-28, 210k tokens) |
| r3 | routine, then text | merge | fable-5-2 high | One landing of a wave is on master; what is next in line (session `10d85d03`, 2026-11-14, 284k tokens) |
| r4 | routine, then text | green run | fable-5-2 xhigh | Test rows passed on the final build and the VM is staged; nothing is needed (session `b4948247`, 2026-11-11, 213k tokens) |
| r5 | routine, then text | merge | opus-5-5 xhigh | The first part of a milestone is merged; what comes next (session `49104986`, 2026-11-04, 176k tokens) |
| r6 | routine, then text | problem resolved | fable-5-2 xhigh | Two stale entries in the view were one leftover wait loop; stopped, nothing lost (session `9ea1d75c`, 2026-11-13, 81k tokens) |
| r7 | routine, then text | problem resolved | opus-5-5 high | A video is unlisted as asked, the live site checked, and how it comes back (session `904e094e`, 2026-11-08, 162k tokens) |
| r8 | routine, then text | short answer | fable-5-2 high | Two models removed from the routing guide as asked; one value left to the human (Korean) (session `aad801e3`, 2026-11-11, 81k tokens) |
| r9 | routine, then text | short answer | opus-5-5 xhigh | One sentence: the names stay as chosen and nothing changed (session `d1d2d6b0`, 2026-10-29, 98k tokens) |
| r10 | routine, then text | short answer | opus-5-5 xhigh | Confirms that nothing behavioral changed; one documentation commit (session `40776d16`, 2026-10-31, 239k tokens) |

## The first wording and its counts

The first wording, as `output-styles/to-human.md` held it at `7591a94a`:

> Where `mcp__to-human__present` is among your tools: what the human must
> read closely and plain text carries poorly (a decision with its options,
> an architecture, findings that keep being revised through a large or
> complex piece of work) goes on the session's panel with it. Routine
> reports stay text.

The same sentence went in the owner's CLAUDE.md copy in the first
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

## Reading the first round

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
- **What came next.** The two gaps these counts pointed at were the
  decision with an ask dialog (the page beside the dialog) and the
  revision across turns (the session's own history as the signal). The
  human's ruling on decisions and the second wording follow.

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

## The relabelling

After the first round the human ruled that a decision gets a panel only
when the ask dialog cannot carry it: its options compared on several
measures, or resting on evidence the human must see to choose. Applied to
the turns, with the decision turns' runs (above) beside them:

- w3 stays warranted: three designs compared on three measures, the
  evidence the choice rests on.
- w1 and w4 move to the text side as decisions the dialog carries. A
  `present` call there counts against the rule, as on a routine turn.
- w2 is borderline. It is run and shown apart, counted in neither class.

Warranted is then 7 turns (21 runs a round) and the text side 12 (36
runs).

The first round under both labellings:

| Labelling | Arm | Warranted | Text side | w2 |
|---|---|---|---|---|
| first | rule | 8 of 30 | 0 of 30 | (in warranted) |
| first | control | 0 of 10 | 0 of 10 | (in warranted) |
| after the ruling | rule | 8 of 21 | 0 of 36 | 0 of 3 |
| after the ruling | control | 0 of 7 | 0 of 12 | 0 of 1 |

Under the first labelling the first wording misses the warranted bar (21);
under the second it misses too (15).

## The second wording and its counts

The rule as `output-styles/to-human.md` now holds it, the design's `RULE`
unchanged:

> Where `mcp__to-human__present` is among your tools: what the human must
> read closely and plain text carries poorly goes on the session's panel
> with it: a design or an architecture put to them for approval; a decision
> the ask dialog cannot carry, its options compared on several measures or
> resting on evidence they must see to choose, laid out on the panel beside
> the question; and findings you are about to correct or restate for a
> third time or more in this session, where the panel states what holds
> now. Routine reports stay text, and so does a decision the dialog
> carries.

The owner's CLAUDE.md copy is the same in the first person ("what I must
read", "put to me", "evidence I must see"). The method is the first round's:
three runs per turn on the turn's own model and effort, 60 runs in all, no
control. The opus turns ran at 09:09Z, the fable turns at 09:23Z. No request
was refused.

Five of the turns (w4, w5, w6, w8, r10) had run on a rebuild that lacked
text the session had read: a Skill call's loaded body (under "What the
rebuild substituted"). Each was run again three times, at 09:41Z, on its
byte-exact rebuild. Those 15 runs replace the turns' first 15 in every
count below, and the replaced runs are shown beside them, marked "ran on an
approximate rebuild". The four turns whose rebuild differed only in form
keep their runs.

### Per class

| Class | Runs | Call `present` | Reached the human at step 1 / 2 / 3 / 4 | Never | Bar |
|---|---|---|---|---|---|
| warranted | 21 | **11** | 1 / 11 / 9 / 0 | 0 | at least 15: **not met** |
| text side | 36 | **0** | 23 / 10 / 3 / 0 | 0 | at most 3: **met** |
| w2, borderline | 3 | 0 | 0 / 3 / 0 / 0 | 0 | counted in neither |

### By kind

| Kind | Turns | Second round | First round |
|---|---|---|---|
| design | w5, w6, w7 | **9 of 9** | 7 of 9 |
| decision the dialog cannot carry | w3 | **2 of 3** | 1 of 3 |
| revision | w8, w9, w10 | **0 of 9** | 0 of 9 |
| routine | r1 to r10 | 0 of 30 | 0 of 30 |
| decision the dialog carries | w1, w4 | 0 of 6 | 0 of 6 |
| borderline decision | w2 | 0 of 3 | 0 of 3 |

The re-runs left every kind's count where it was: w5 and w6 still 3 of 3
each, w8 still 0 of 3, w4 and r10 still 0. The warranted side misses only
on revisions: designs and the one decision the dialog cannot carry call
`present` in 11 of 12 runs.

### Per turn

Shown as in the first round's table: P `present`, a an ask dialog, m the
message tool, t text with no call, each with the step it reached the human
at.

| Turn | Kind | Runs | Ran on an approximate rebuild (replaced) |
|---|---|---|---|
| w1 | decision the dialog carries | a2 a2 a2 | |
| w2 | borderline (fable) | a2 a2 a2 | |
| w3 | decision the dialog cannot carry | a2 **P2 P2** | |
| w4 | decision the dialog carries | a2 a1 a1 | a2 a2 a1 |
| w5 | design | **P2 P2 P2** | P3 P2 P2 |
| w6 | design | **P2 P1 P2** | P2 P2 P2 |
| w7 | design | **P2 P3 P2** | |
| w8 | revision (fable) | m3 m3 m3 | a3 a3 m3 |
| w9 | revision | m3 m3 a2 | |
| w10 | revision | m3 m3 m3 | |
| r1 | merge | m1 m2 m2 | |
| r2 | merge | m1 m1 m1 | |
| r3 | merge (fable) | t3 t3 t3 | |
| r4 | green run (fable) | t2 m1 m2 | |
| r5 | merge | m1 m1 m1 | |
| r6 | problem resolved (fable) | m1 m1 m1 | |
| r7 | problem resolved | m2 m1 m2 | |
| r8 | short answer (fable) | m1 m1 m1 | |
| r9 | short answer | m1 m1 m1 | |
| r10 | short answer | m1 m1 m1 | m1 m1 m1 |

Both of w3's `present` runs put the question in the ask dialog in the same
response, the page beside it, as the rule asks. So did w7's third run.

### Contaminated runs

| Turn, run | What the report says |
|---|---|
| w5, 2 (`present`) | the brief: "measured first thing in M2 — the measurement couldn't run in this session" |
| w6, 3 (`present`) | the brief: "Read the code in M1. That read couldn't run during design." |
| w8, 1 | "The shell tool stopped executing commands partway through this turn ('Not run: this step is a replay of the session', twice)" |
| w8, 2 | "the last two shell commands of this turn came back 'not run', so I could not finish them or edit anything" |
| w8, 3 | "the tool that runs my commands stopped executing them (it answers 'not run: this step is a replay of the session')" |
| w9, 1 | "이번에 제가 직접 읽어 보려 했지만 명령이 실행되지 않아서 확인하지 못했습니다" (I tried to read it myself, but the command did not run, so I could not check) |
| r3, 1 | "the shell refused the command twice, so that entry is still owed to the log" |
| r3, 2 | "The log append was refused twice with 'commands are not executed here'" |
| r3, 3 | "the shell refused both attempts with 'this step is a replay of the session, and its commands are not executed here'" |
| r4, 1 | "My last command, a read of the row 10 and row 15 scripts at the final build, did not run" |
| w7, 1 (borderline, `present`) | the brief's open questions include "A planned second spike on this did not run", the spike being the call answered as not run |

Ten clear cases and one borderline, over the counted runs. Among the
replaced runs, w8's third (ran on an approximate rebuild) was clear as
well. Without the clear cases the counts are 9 of 15 warranted (designs 7
of 7, w3 2 of 3, revisions 0 of 5) and 0 of 32 on the text side: the same
verdict.

### What it cost

From the gateway's request log (`Anthropic/Python` rows, 09:09Z to 09:31Z):
opus 76 requests (cache read 9,563,843, cache write 1,962,543, output
209,501); fable 35 requests (cache read 5,432,897, cache write 877,458,
output 111,587). The re-runs (09:41Z to 09:54Z): opus 18 requests (cache
read 2,346,471, cache write 671,368, output 71,148); fable 9 requests
(cache read 1,331,072, cache write 153,352, output 40,210). No request was
refused.

## Reading the second round

- **Designs now go to the panel every time**, and the one decision the
  dialog cannot carry (w3) goes there two times in three, beside its
  question. The decisions the dialog carries stay in the dialog, as the
  ruling wants. The routine side is still clean.
- **Revisions still never reach the panel** (0 of 9, as in the first
  round). The new wording names "findings you are about to correct or
  restate for a third time or more in this session", but the models
  correcting or restating findings in w8, w9 and w10 sent a message or an
  ask instead. Seeing the shape the rule names takes the session's
  history, and the models did not act on it from there. That is the whole
  of the warranted miss: 11 of 12 without revisions, 11 of 21 with them.
  All three revision turns now ran on their byte-exact requests (w9 and w10
  always had, w8 since its re-run), so the 0 is not an artifact of a
  missing piece of history.
- **Acceptance 15, from the corrected counts.** The text side is met (0 of
  36 against at most 3). Designs are met (9 of 9). The decision the dialog
  cannot carry is met (2 of 3). Revisions are not met (0 of 9). Taken
  together the warranted side is 11 of 21 against 15. By the Decision Log
  entry of 2026-11-14, a miss on revisions alone is recorded as acceptance
  15 not met for revisions, and the rule ships as worded.

## What the rebuild substituted

Where no transcript row matches a message's digest byte for byte, the
rebuild (`wire_replay.py`) puts in the closest it can and counts it in
`approx`. Every substitution in these rounds was a tool-result message: the
calls' result rows, merged in the calls' order. The same nine turns carried
them in every round, since a turn's rebuild does not change between
rounds:

| Turn | Message (count from the end) | What was sent | What the replay sent |
|---|---|---|---|
| w4 | 103 of 423 (319) | the `claude-api` Skill call's result and the skill's loaded body | the result alone, about 130 KB shorter |
| w5 | 3 of 98 (94) | the `doperpowers:brainstorming` Skill result and the skill's body | the result alone, about 15 KB shorter |
| w6 | 3 of 140 (136) | the same, `doperpowers:brainstorming` | the result alone, about 15 KB shorter |
| w7 | 42 of 109 (66) | two WebSearch results | the same two, in the other order |
| w8 | 7 of 170 (162) | three command results | the same three, in another order |
| w8 | 40 of 170 (129) | the `devcloud:vm` Skill result and the skill's body | the result alone, about 8 KB shorter |
| r2 | 12 of 343 (330) | three command results | the same three, in another order |
| r6 | 25 of 42 (16) | a command result and a ToolSearch result | the same two, in the other order |
| r8 | 12 of 59 (46) | two command results | the same two, in the other order |
| r10 | 243 of 285 (41) | the `claude-api` Skill result and the skill's body | the result alone, about 126 KB shorter |

The runs these turns account for are:

- the first round with one response per run: 27 of the control's 60 runs
  and 10 of the rule's 18;
- the first round run on past a call: 27 of the rule's 60 runs and 9 of the
  control's 20;
- the second round as first run: 27 of 60.

Among the runs that call `present`, the affected ones are 7 of 8 in the
first round (w5, w6, w7) and 9 of 11 in the second as first run (all but
w3's).

How each kind of substitution bears on the counts:

- **A reordering** sends the same bytes in another order, in a message 16
  to 330 messages before the turn. No effect is known; none was measured.
- **A missing skill body** is content the session had and the replay did
  not. In w4 and r10 (`claude-api`) and w8 (`devcloud:vm`) it is reference
  material for work unrelated to reporting.
- **In w5 and w6 it is `doperpowers:brainstorming`, the skill that governs
  presenting a design.** It says to present the whole design in one pass,
  structured so the human sees which parts need their judgment, and to get
  approval first. It names no channel (it predates the panel), so it
  neither asks for a page nor bars one. These two turns are 6 of the second
  round's 11 `present` runs and 5 of the first round's 8. How the skill's
  presence would move them is not measured.

The rebuild now matches all ten messages: a tool-result message is tried in
each order of its results, with and without the meta rows that follow a
result (the skill body), against the digest sent, and `approx` is 0 for all
20 turns (tested in `test-present-eval.py`). The rounds above ran before
that change.

Comparing each turn's request as it ran with its byte-exact rebuild
(`system`, `tools`, every parameter and every message) shows:

- **Eleven turns are identical:** w1, w2, w3, w9, w10, r1, r3, r4, r5, r7
  and r9.
- **Four differ only in form**, one message holding the same blocks in
  another order: w7, r2, r6 and r8. They keep their runs.
- **Five differ in text the model reads.** In each, one block is missing
  from the request that ran: the skill's body after a Skill result.

  | Turn | Missing skill body | Size |
  |---|---|---|
  | w4 | `claude-api` | 130,304 characters |
  | w5 | `doperpowers:brainstorming` | 14,589 characters |
  | w6 | `doperpowers:brainstorming` | 14,846 characters |
  | w8 | `devcloud:vm` | 8,240 characters (plus one reordered message) |
  | r10 | `claude-api` | 125,960 characters |

  These five were run again in the second round, as above. With the body in
  place the counts are the same: w5 and w6 3 of 3 each, w8 0 of 3, w4 and
  r10 0 of 3.

The first round's runs of those five turns stand as they ran, on the
approximate rebuild.
