# Parallel milestones: a Plan of Work declares a group, the loop runs it in worktrees and lands it through a merge queue

## Purpose

A spec whose Plan of Work has a fan-out shape — one milestone that lays an
interface, several that build on it without touching each other, one that
wires them together — finishes today in the sum of its milestones'
durations, because doperpowers:subagent-driven-execution (SDE: the loop
that runs a spec's milestones through fresh executor subagents,
`skills/subagent-driven-execution/SKILL.md`) dispatches one executor at a
time in one shared checkout. After this change the spec can declare that
shape in one line, and the loop runs the group's members at once, each in
a worktree of its own, reviews each where it was written, and lands them
one at a time onto the execution branch — so the spec finishes in the
wall-clock of its longest path with the same review at every boundary. A
spec that declares nothing runs exactly as it does today.

How to see it working: this spec's own Plan of Work declares
`Order: {M1, M2} → M3`. Once it has been executed, the SDE ledger for it
shows two milestones executed on separate branches in separate worktrees
and landed by fast-forward, and `git log --merges` on the branch shows no
merge commit (Acceptance, item 1).

Prior record. `docs/doperpowers/specs/2026-08-21-task-grain-and-review-cadence-design.md`
§4 deferred parallel executors: tasks in one plan routinely touched the same
files and no merge design existed.
`docs/doperpowers/specs/2026-09-04-plan-resolution-and-document-tree-design.md`
named an interface DAG in the plan as the prerequisite. The 2026-09-12 fold
(`docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`,
its 2026-09-26 Decision Log entry) delivered it: milestones name the
interfaces they produce and consume, and the loop already reviews at
dependency frontiers derived from them. What remained was the checkout,
and the merge design this document supplies. Outside this repo, spec-kit
marks parallel-safe tasks `[P]` under the rule "different files, no
dependencies", Kiro places tasks on a dependency graph, and every merge
queue (Bors, GitHub's) lands candidates one at a time and tests each at the
tip — the property the landing section below keeps.

## Progress

- [ ] M1 — the shape in the spec
- [ ] M2 — the group wave and the landing
- [ ] M3 — tests, docs, version, and the acceptance walk

## Terms

- **Milestone**: one entry of a spec's Plan of Work, headed
  `### M<N> — <title>`; the unit one executor owns
  (`skills/execspec/references/living-spec.md`, "Sizing a milestone").
- **Controller**: the session running the SDE loop — the spec's author
  session, or a `doperpowers:plan-executor` subagent. The spec's one writer
  while the loop runs.
- **Executor**: a `doperpowers:task-executor` subagent owning one milestone.
- **Execution branch**: the branch the controller's isolated checkout is on;
  every milestone lands here and the whole-branch review reads it.
- **Tip**: the execution branch's current commit.
- **Group**: milestones that may run at the same time, declared in the
  Order line; a **member** is one of them.
- **Fork commit**: the tip at the moment a group dispatches; every member's
  branch starts there, and it is every member's review BASE.
- **Landing**: moving a reviewed member's commits onto the execution branch —
  a fast-forward of the branch onto the member's branch (git moves the
  branch pointer forward; no merge commit), after a rebase when the tip
  moved.
- **Workspace**: `.doperpowers/sde/<spec-slug>/` in the controller's
  checkout, resolved by `skills/subagent-driven-execution/scripts/sde-workspace`;
  it holds the ledger, reports, and review packages and is gitignored by
  its own `.gitignore`.
- **Ledger**: `<workspace>/progress.md`, the loop's recovery record.

## The shape, in the spec

A Plan of Work is a list and runs in listed order. When it has a fan-out,
one line opens the section, before the first milestone heading:

    Order: M1 → {M2, M3, M4} → M5

The grammar is in Interfaces and Dependencies. The line is present only
when the plan has at least one group; a plan with none carries no line, and
nothing about its execution changes. That keeps every serial spec
attributable in the monitoring readout the 2026-09-12 fold is under: the
feature is inert unless a spec asks for it.

Why one line rather than a graph: a per-milestone `After:` line is a
dependency graph proper, but parallelism is then implied by two entries
naming the same predecessor, and the group's conditions have no single
place to be checked; spec-kit's `[P]` marker on a heading is terser still
but leaves the group's boundary implicit. One line shows the whole shape at
a glance and gives the self-review, the buildability review, and the loop's
pre-flight one target.

**The group conditions.** A group holds milestones that satisfy all three:

1. No member consumes an interface another member produces. Interfaces and
   Dependencies names producers; a member's interfaces come from milestones
   before the group. A contract the spec's Interfaces section already fixes
   is the spec's, not the first milestone's that implements it: two members
   may implement the same spec-owned contract independently, each from the
   document.
2. Members' "what it touches" sets are disjoint — no path appears under two
   members.
3. Each member can be verified in a checkout of its own: the repository's
   suite runs in two worktrees at once without collision (no fixed port, no
   shared database, no shared scratch path). The spec's opening constraints
   assert this; where they cannot, the plan stays serial. The alternative —
   members run only their focused tests and the controller runs the full
   suite at each landing — reaches more repositories, but it costs the
   executor's full-suite-before-commit evidence, and a cross-cutting break
   surfaces one step later than it should.

One level of grouping: a chain inside a group is a sign the group is drawn
wrong. The last milestone runs acceptance on the whole branch and is never
a member. No cap on a group's size in doctrine — the harness's concurrency
bounds it, and a group of many members is doperpowers:decomposing's split
signal, not a plan shape.

Where the rule lives: `skills/execspec/references/living-spec.md`, a
paragraph "Ordering the milestones" after "Sizing a milestone", plus the
optional line in its Plan of Work skeleton. execspec's self-review (step 2
of `skills/execspec/SKILL.md`) checks a declared group against the group
conditions, by that name. The adversarial buildability review reads the
same doctrine. SDE's pre-flight (its step 2) checks the group against the
code — the touch sets in fact, the suite in fact — and a group that fails
runs serially, with a dated Decision Log entry naming the condition that
failed; that is a technical call, not a fork under brainstorming's gate.

## The group wave, in the loop

Reaching a group in the Order line, the controller:

1. Records the fork commit (the tip) in the ledger.
2. Creates one worktree per member under the workspace, on a branch named
   for the milestone, run from the checkout:

       git worktree add <workspace>/wt-<N> -b sde/<spec-slug>/M<N> HEAD

   Nested under the workspace, the worktree sits inside the controller's
   own checkout path and under the workspace's self-ignoring `.gitignore`,
   so `git status` in the checkout stays clean, and the harness's
   worktree-isolation guard — which refuses git that leaves the session's
   worktree — is satisfied (Surprises & Discoveries, first entry).
3. Dispatches every member at once: the same executor dispatch as a serial
   task plus two lines, the member's worktree as the directory to work from
   and the branch to commit on (Interfaces and Dependencies, "Dispatch
   lines"). The report path is absolute, in the workspace, as today.

Why a manual `git worktree add` rather than the harness's own subagent
isolation (`isolation: worktree` on the Agent call): that isolation
branches from the remote default branch unless a user-level setting
(`worktree.baseRef: "head"`) says otherwise, so a member would start
without the milestones already on the execution branch, and a plugin cannot
set a user's settings; and the controller must own the worktree's lifecycle
to land it. The isolated-workspace reference's "native tool first" rule is
about the session's own checkout, which the harness must be able to follow;
a member's worktree is short-lived and the controller's.

The executor, in a fresh worktree, runs the repository's setup before
anything else — a fresh checkout has no dependencies installed and no
build; when the repository declares `.doperpowers/repo-facts.md`, its
bootstrap facts say what — and addresses its worktree by path in every
command, because a subagent's `cd` does not persist between tool calls. It
works and commits on its branch as any task; its contract is otherwise
unchanged: whole spec read, decide and log, self-review, report.

As each member returns, the controller folds its decisions and discoveries
into the spec as SDE's step 4 says. Two members that resolved the same
unforeseen gap differently — one error semantics decided two ways, a name
chosen twice — are reconciled in the Decision Log once every member has
returned and before the landing phase opens (Landing, below), and the
member on the losing side is resumed with the fix. Disjoint files do not
prevent this case, which is why no member lands before every sibling's
decisions are in view. The controller being the spec's one writer is what
makes the reconciliation safe: no member edits the spec, so the document
itself never conflicts.

Each member is reviewed as it returns, in its own worktree. The review
package is `scripts/review-package SPEC_FILE <fork> <member HEAD>` —
packages read the shared object store, so a member's branch packages from
the checkout — and the reviewer dispatch's checkout line names the
member's worktree as the tree its focused tests run in. Reviewers run
concurrently under SDE's existing rule (hermetic suites together; suites
that share state one at a time), and the third group condition makes them
hermetic. Findings resume the member's executor in its worktree, as today.

## Landing

Landing is a phase of the group. It opens when every member has returned
and the controller has folded and reconciled their decisions; until then a
clean member waits. The milestone after the group cannot dispatch before
the last landing anyway, so opening the phase at the last return costs no
wall-clock, and it is what makes "reconciled before any member lands" a
rule the controller can keep. Within the phase, members land one at a time,
each as soon as its review is clean — a member still in a fix loop lands
when its verdict comes clean; the group is order-independent by
construction, and a declared landing order would idle a finished member
behind an unfinished one. One landing at a time also means no two rebases
ever race against a moving tip.

A clean verdict is bound to the head it reviewed: the ledger records
`approved <sha7>`. A member lands only when its branch head is that
approved head or reached it through rebases recorded `clean` (the patch
did not change); any other head — a rebase that resolved conflicts, a
commit the ledger does not name — is reviewed on `<onto>..<head>` before it
lands. A recovering controller applies the same rule and never infers an
unchanged patch from a rebase that succeeds now: a conflict resolved
earlier is still unreviewed code.

| Tip since the fork | What happens |
|---|---|
| Unmoved (the first to land) | The controller fast-forwards: `git merge --ff-only sde/<spec-slug>/M<N>` in the checkout. |
| Moved; rebase clean, suite green | The controller resumes the member's executor to rebase its branch onto the tip in its worktree and run the full suite; it reports the rebased range. The ledger records `rebased <head> onto <tip> clean`; the approved verdict still covers the patch, and the controller fast-forwards. |
| Moved; conflicts resolved, or code changed to make the suite pass | The executor rebases, resolves each conflict the way the spec's intent and the siblings' Decision Log entries point, runs the full suite, and reports the rebased range and every file it resolved. The ledger records `rebased <head> onto <tip> resolved <files>`. The reviewer is resumed on the rebased range (`review-package SPEC_FILE <tip> <rebased HEAD>`, told it is the same task rebased and which files carried conflicts); its clean verdict is a new `approved` line, and then the controller fast-forwards. |
| The rebase needs a decision the spec leaves open | The executor stops with BLOCKED; it is a fork under brainstorming's gate like any other and goes to whoever dispatched the controller. |

The executor's full suite on the rebased tree is the run a merge queue
makes: the member's commits on top of everything landed before it. That is
where a semantic conflict — two members green alone and red together —
surfaces, at the second landing, and it is that member's executor's fix.
Git's textual conflicts are the same case one step earlier.

Why the executor rebases and the controller fast-forwards: each git command
then runs inside its caller's own worktree, which is what the isolation
guard checks; and the executor holds the task's context, so a conflict is
resolved by the agent that wrote the code rather than by the controller's
hands (SDE: "Fix through a worker, not your own edits"). Why rebase then
fast-forward rather than a merge commit per member: history stays linear,
so the ledger's `base..head` ranges, the review packager, and the
deferred-review bookkeeping work unchanged; a merge commit would keep the
report's commit SHAs valid, but a task's range would no longer be a
straight line.

Right after the fast-forward, before any cleanup, the controller appends
the member's `landed <onto>..<head>` line: from then on the ledger says
the landing happened, whatever is interrupted next. Then it removes the
member's worktree and branch — its own to remove, once the landing is
recorded (`skills/subagent-driven-execution/isolated-workspace.md`, "At
finish"); both removals are retryable cleanup, and one that finds nothing
to remove is done — appends the `complete` line, and ticks the milestone
in Progress: a tick on a member means reviewed clean and landed. The
milestone after the group dispatches when every member has landed.

Member states, for the record a recovering controller reads:

| State | Event | Next | Controller does |
|---|---|---|---|
| executing | executor returns DONE or DONE_WITH_CONCERNS | returned | fold decisions and discoveries; reconcile against siblings |
| executing | BLOCKED or NEEDS_CONTEXT | executing | SDE's executor statuses, unchanged |
| returned | fold committed | reviewing | package `<fork>..<HEAD>`; dispatch the reviewer with the worktree as its checkout line |
| reviewing | needs fixes | reviewing | resume the executor in its worktree; re-review the fix range |
| reviewing | approved | clean | ledger `approved <head>` |
| clean | landing phase not open (a sibling has not returned, or decisions are not yet reconciled) | clean | wait; a reconciliation that goes against this member resumes its executor with the fix → reviewing |
| clean | phase open; tip is the fork commit or the commit this member was last rebased onto | landed | fast-forward; ledger `landed`; remove worktree and branch; ledger `complete`; tick Progress |
| clean | phase open; tip moved | landing | resume the executor: rebase onto `<tip>`, full suite, report |
| landing | rebase clean, suite green | clean | ledger `rebased <head> onto <tip> clean`; the approval still covers the patch |
| landing | conflicts resolved, or code changed | reviewing | ledger `rebased <head> onto <tip> resolved <files>`; resume the reviewer on `<tip>..<rebased HEAD>` |
| landing | needs an open decision | stopped | the gate fork goes up |
| landing | suite red | landing | the executor fixes on its rebased branch; then as "code changed" |

## Recovery

The ledger binds each member's state to commits (Interfaces and
Dependencies, "Ledger lines"): its branch and worktree, its `head`, the
`approved` head, every `rebased … onto … clean|resolved` line, and
`landed`. Every member line starts with `Task N:`, because members return
concurrently and a bare continuation line would not say whose it is. After
compaction, or in a new controller, for each executed member without a
`complete` line:

- A `landed` line is present, or its latest head is already an ancestor of
  the execution branch (`git merge-base --is-ancestor <sha> HEAD`): the
  landing happened. Finish the cleanup — a worktree or branch already gone
  is done — and write `complete`.
- Otherwise its branch exists, since a branch is deleted only after
  `landed`. Recreate the worktree if it is gone
  (`git worktree add <workspace>/wt-<N> sde/<spec-slug>/M<N>`) and resume
  at the state the lines imply: no `reviewer`, dispatch the review;
  `reviewer` and no `approved`, resume it; an `approved` head that is the
  branch head, or joined to it only by `rebased … clean` lines, is clean
  and lands when the phase is open; any other head — a `rebased … resolved`
  with no later `approved`, or a head the ledger does not name — is
  reviewed on `<onto>..<head>` first. A rebase that succeeds now says
  nothing about whether the patch changed earlier.

The committed spec's Progress is the human-readable state, as today.

## What does not change

Serial specs, and every spec without an Order line. The task reviewer's
rubric and read-only posture. The model tiers. `doperpowers:plan-executor`,
which runs the loop through the SDE skill and inherits the group wave
without a word of its own. doperpowers:decomposing's parallelism, which
runs composite children on separate branches with separate pull requests —
a group is for pieces below decomposing's gate that share one branch and
one acceptance run. `scripts/sde-workspace` and `scripts/review-package`
work unchanged, and no script is added: the landing is four plain git
commands.

## Acceptance

Behavior an agent reading the documents produces, and this initiative's
own run:

1. **A group runs as a group.** After this spec's M1 and M2 have been
   executed, the ledger for this spec (`<workspace>/progress.md` in the
   controller's checkout) contains one `Group {M1, M2}: fork <sha7>` line
   and one `Group {M1, M2}: landing open` line; a `Task 1: executed (…,
   branch sde/2026-09-27-parallel-milestones-design/M1, worktree wt-1)`
   line and the same for Task 2 with `M2` and `wt-2`; `Task 1: approved`
   and `Task 2: approved` lines; `Task 1: landed` and `Task 2: landed`
   lines; and `Task 1: complete (…)` and `Task 2: complete (…)` lines each
   ending `landed)`.
   `git log --oneline --merges <fork>..HEAD` prints nothing;
   `git log --oneline <fork>..HEAD` shows M1's and M2's commits in one line
   of history; `git worktree list` shows no `wt-1` or `wt-2`;
   `git branch --list 'sde/*'` prints nothing.
2. **The second landing rebased.** Whichever member landed second has a
   `Task N: rebased <sha7> onto <sha7> clean` line in the ledger, and
   Surprises & Discoveries records which member it was and that the rebase
   was clean. This spec's members
   touch disjoint files, so the landing table's conflict rows are not
   exercised here (Decision Log, verification entry).
3. **A spec without an Order line reads unchanged.**
   `grep -c "One executor at a time" skills/subagent-driven-execution/SKILL.md`
   prints at least `1` — the serial rule for the shared checkout is still
   stated —
   and `grep -c "Order:" skills/execspec/references/living-spec.md` prints
   at least `2` (the rule and the skeleton), with the rule stating that the
   line is present only when a group exists.
4. **The group conditions are stated once and cited by name.**
   `grep -c "group conditions" skills/execspec/references/living-spec.md skills/execspec/SKILL.md skills/subagent-driven-execution/SKILL.md`
   prints a count of at least `1` for each of the three files.
5. **The executor knows a fresh worktree and a landing request.**
   `grep -c "setup" agents/task-executor.md agents/codex/task-executor.toml`
   and `grep -c "rebase" agents/task-executor.md agents/codex/task-executor.toml`
   each print at least `1` for both files.
6. **Suites.** From the checkout root:
   `bash tests/issue-tracker/test-protocol-content.sh` exits 0;
   `bash tests/claude-code/test-sde-workspace.sh` exits 0;
   `python3 tests/codex/test-native-agents.py` exits 0;
   `scripts/lint-shell.sh` reports nothing beyond its baseline.
7. **Version.** Every file `.version-bump.json` lists carries the same
   version, one minor above `main`'s at merge time.

## Plan of Work

Order: {M1, M2} → M3

Constraints that bind every milestone:

- The project's voice ("your human partner") and the golden rule
  (`CLAUDE.md`, "Simplicity-First Protocols"): state ownership and
  outcomes; a hard rule only where the failure is definite. Distill; the
  spike in Surprises & Discoveries is evidence for a rule, not a case study
  to encode.
- Each thing once, in the section that owns it; other sections point
  (living-spec.md, "What the document carries"). The group conditions live
  in living-spec.md; execspec and SDE cite them by name.
- No line ranges in prose; repository paths only.
- Commit messages carry no attribution footers.
- Codex mirrors (`agents/codex/task-executor.toml`,
  `agents/codex/task-reviewer.toml`) carry the same body text as their
  Claude definitions, as they do today.
- Shell files pass `scripts/lint-shell.sh`; no new scripts.
- The suite runs hermetically per worktree: every test this initiative runs
  is a shell or Python script over the repository's own files, with no port
  or shared state (group condition 3).

### M1 — the shape in the spec

At its end, an author writing a spec through execspec finds in
living-spec.md how to declare a group and what a group may hold, and
execspec's self-review tells them to check it.

Touches: `skills/execspec/references/living-spec.md`;
`skills/execspec/SKILL.md`.

Interfaces: implements the Order line grammar and the group conditions —
contracts this spec owns (Interfaces and Dependencies) — in the doctrine.
It produces nothing M2 reads; M3's tests consume its text.

Decisions for this milestone. The paragraph is **"Ordering the
milestones."**, placed directly after "Sizing a milestone" and before "What
a milestone carries". It states the default (listed order, serial); the
line and when it is present; the grammar by example; the three conditions
as a numbered list under the name "the group conditions"; one level of
grouping; the last milestone never a member; and one sentence on why one
line, the alternatives above in a clause. The Plan of Work skeleton in "The
execution section" gains the optional line under `## Plan of Work`, with a
bracketed note that it appears only when milestones may run in parallel.
In "What a milestone carries", the sentence "The controller schedules
reviews from these" extends to parallel dispatch where an Order line
declares a group. The "While the spec is being executed" section's sentence
on several milestones gains one clause: a group in the Order line runs its
members at once, each in a worktree of its own, landed one at a time — a
pointer to SDE, which owns the mechanics. In `skills/execspec/SKILL.md`,
step 2's self-review gains one clause: a declared group is checked against
the group conditions. No other execspec text changes.

Does not touch: SDE and its references, agents, tests, docs, version.

Proves: acceptance 3 (the living-spec half) and 4 (the two execspec files).

### M2 — the group wave and the landing

At its end, a controller reading the SDE skill runs a declared group in
parallel worktrees and lands it as the design above says, and an executor
reading its definition knows what a fresh worktree and a landing request
ask of it.

Touches: `skills/subagent-driven-execution/SKILL.md`;
`skills/subagent-driven-execution/isolated-workspace.md`;
`agents/task-executor.md`; `agents/codex/task-executor.toml`;
`agents/task-reviewer.md`; `agents/codex/task-reviewer.toml`.

Interfaces: implements the same spec-owned contracts — the Order line
grammar and the group conditions, cited by name — and the ledger lines and
dispatch lines (Interfaces and Dependencies), in the loop's text. It
produces nothing M1 reads; M3's tests consume its text.

Decisions for this milestone. In the SDE skill: step 1 reads the Order line
when present; step 2's pre-flight checks a declared group against the group
conditions in the code and demotes a failing group to serial with a dated
Decision Log entry; step 3 keeps "One executor at a time" for the shared
checkout and adds the group wave — fork commit, worktrees under the
workspace with the branch name, dispatch at once, the two extra dispatch
lines; step 4 adds the reconciliation of members that contradict each
other, run once every member has returned; step 5 adds review in the
member's worktree as it returns, with the clean verdict recorded as
`approved <head>`; a new step between today's 6 and 7, **Land**, carries
the landing phase (opens at the last return, after reconciliation; one
landing at a time), the approval-covers-the-head rule, the landing table's
four rows in prose, and the order fast-forward → `landed` line → cleanup
→ `complete` → tick; step 7 says a member's tick means reviewed clean and
landed, and the milestone after the group waits for the whole group;
"Durable progress" gains the group lines, the `Task N:` prefix on every
member line, the `approved`, `rebased … onto … clean|resolved`, and
`landed` lines, and the recovery rules of the Recovery section — the
ancestor check for a landing interrupted before its ledger line, and the
approval-coverage rule that never infers an unchanged patch from a rebase
that succeeds now; "Dispatch hygiene" gains the member's two lines and the
reviewer's worktree checkout line. The design's reasoning is not restated in the
skill — one clause each on why the worktree is manual and nested, why the
executor rebases and the controller fast-forwards, and why linear. The
group wave is a variant of the loop, not a second loop: the skill grows by
tens of lines, not a section per state.

In `isolated-workspace.md`, under "Native tool first", one sentence: when
the shell's commands are refused after entering a worktree because its
working directory stayed in the main checkout, exit the worktree keeping
it and re-enter it by path (Surprises & Discoveries, third entry).

In `agents/task-executor.md`: "Before You Begin" gains the fresh-worktree
sentence — setup first, repo-facts bootstrap when the repository declares
one, address the worktree by path since `cd` does not persist between tool
calls; a paragraph after "While you work" carries the landing request —
rebase onto the named tip in your worktree, resolve conflicts in the spirit
of the spec and the siblings' Decision Log entries, run the full suite,
report the rebased range and the resolved files, and a conflict that needs
a decision the spec leaves open is a BLOCKED stop. The Codex mirror carries
the same text.

In `agents/task-reviewer.md`, the sentence on where a focused test runs —
"the detached worktree the controller names when the dispatch carries a
checkout line" — becomes "the worktree the controller names when the
dispatch carries a checkout line", since a member's worktree is not
detached; nothing else changes. The Codex mirror the same.

Does not touch: living-spec.md, execspec, tests, docs, version.

Proves: acceptance 3 (the SDE half), 4 (the SDE file), and 5.

### M3 — tests, docs, version, and the acceptance walk

At its end the content tests pin the new statements, the docs describe the
shape, the version is bumped, and every acceptance item has been run with
its output recorded in the report.

Touches: `tests/issue-tracker/test-protocol-content.sh` (the task-executor
setup and landing statements in both harnesses' definitions; the
task-reviewer wording; the SDE skill's Land step and its "group conditions"
citation; living-spec's "Ordering the milestones" and its "group
conditions"); `tests/codex/test-native-agents.py` only where it asserts
task-executor body text; `README.md` (the flow diagram's SEVERAL line and
the two skill-list lines for SDE say a declared group runs its members in
parallel worktrees); `CLAUDE.md` (the agents row's task-executor clause and
the skills row's SDE mention, one clause each);
`docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`
(one dated line in its Decision Log: this spec is the readout's first
initiative and adds the group-run measures its verification entry lists);
the version, through `scripts/bump-version.sh`.

Decisions for this milestone. Content tests assert the presence of the
load-bearing statements in the same `assert_contains` style the file uses,
on phrases the statements carry (not whole sentences, which drift): the
Order line rule in living-spec, "group conditions" in the three files, the
Land step in SDE, "setup" and "rebase" in both executor definitions. No
live-agent test is added — `tests/claude-code/test-subagent-driven-execution.sh`
is description-recall and stays as it is. A test that cannot find a
statement M1 or M2 was to write is a finding on that milestone, reported
in the return, not a body edit made here. Docs: one clause per line, no
new section.

Does not touch: skill and agent bodies.

Interfaces: consumes M1's and M2's text — the artifacts, landed on the
branch before this milestone dispatches.

Proves: acceptance 6 and 7, and runs items 1–5 as the acceptance walk,
recording each command and its output in the report. Items 1 and 2 read
the controller's ledger, which sits in the checkout this milestone works
in.

## Concrete Steps

Working directory for every command: the controller's isolated checkout,
the root of this branch's worktree.

The group wave for this spec (the controller runs these):

    skills/subagent-driven-execution/scripts/sde-workspace docs/doperpowers/specs/2026-09-27-parallel-milestones-design.md
    # prints <workspace>
    git rev-parse --short HEAD
    # the fork commit
    git worktree add <workspace>/wt-1 -b sde/2026-09-27-parallel-milestones-design/M1 HEAD
    git worktree add <workspace>/wt-2 -b sde/2026-09-27-parallel-milestones-design/M2 HEAD
    # dispatch both executors; then, on each clean review — after the
    # executor's rebase when the tip moved:
    git merge --ff-only sde/2026-09-27-parallel-milestones-design/M<N>
    git worktree remove <workspace>/wt-<N>
    git branch -d sde/2026-09-27-parallel-milestones-design/M<N>

Expected: `Fast-forward` in each merge's output and never `Merge made by`.

Tests (M3 and the acceptance walk):

    bash tests/issue-tracker/test-protocol-content.sh    # every assertion PASS, exit 0
    bash tests/claude-code/test-sde-workspace.sh          # PASS lines, exit 0
    python3 tests/codex/test-native-agents.py             # OK
    scripts/lint-shell.sh                                 # nothing beyond the baseline

Version (M3):

    scripts/bump-version.sh <next minor>
    git diff --stat    # every file .version-bump.json lists, and nothing else

## Interfaces and Dependencies

**The Order line.** In the Plan of Work, before the first milestone
heading, one line:

    Order: <term> → <term> → … → M<N>

A term is `M<N>` or `{M<N>, M<N>[, M<N>…]}`. Every milestone of the Plan of
Work appears exactly once. The last term is a single milestone. Braces do
not nest. The line is present only when at least one term is a group;
absent, the order is the listed order.

**The group conditions** — living-spec.md is the owner; cited by that name
elsewhere: (1) no member consumes an interface another member produces;
(2) members' touch sets are disjoint; (3) the suite runs per worktree
without collision, asserted in the spec's opening constraints.

**Names.** `<spec-slug>` is the spec file's basename without `.md` — the
string `sde-workspace` uses for the workspace directory. Member branch:
`sde/<spec-slug>/M<N>`. Member worktree: `<workspace>/wt-<N>`.

**Ledger lines**, added to the format in the SDE skill's "Durable
progress":

    Group {M2, M3, M4}: fork <sha7>
    Task N: executed (base <fork7>, executor <handle>, branch sde/<spec-slug>/M<N>, worktree wt-<N>)
    Task N: head <sha7>
    Task N: reviewer <handle>
    Task N: approved <sha7>                         — the head the clean verdict covers
    Group {M2, M3, M4}: landing open                — every member returned; decisions reconciled
    Task N: rebased <sha7> onto <sha7> clean        — or: rebased <sha7> onto <sha7> resolved <files>
    Task N: landed <onto7>..<head7>                 — written right after the fast-forward, before cleanup
    Task N: complete (commits <onto7>..<head7>, review clean, landed)

Every member line starts with `Task N:` (members return concurrently); a
serial task's lines keep today's format. `<onto7>` is the tip the member
was fast-forwarded from: the fork commit for the first to land, the
previous landing for the rest. Fix lines (`fix-base`, `fix-head`) are as
today, prefixed.

**Dispatch lines.** Executor, a member: "Your worktree: `<absolute path of
wt-N>` — run the repository's setup there first. Your branch:
`sde/<spec-slug>/M<N>`." Executor, a landing request: "Rebase
`sde/<spec-slug>/M<N>` onto `<sha7>` in your worktree; resolve conflicts
in the spirit of the spec and its Decision Log; run the full suite; report
the rebased range and every file whose conflict you resolved." Reviewer, a
member: the checkout line reads "The task's tree is at `<absolute path of
wt-N>`; the package is `<fork7>..<head7>`." Reviewer, after a rebase with
conflicts: "Same task, rebased onto `<sha7>`; package `<sha7>..<rebased7>`;
conflicts were resolved in: `<files>`."

## Surprises & Discoveries

- Observation: From inside a harness-isolated session, `git worktree add`
  of a sibling nested under the SDE workspace, `git -C <sibling> commit`,
  `git merge --ff-only <sibling-branch>`, `git worktree remove`, and
  `git branch -D` all ran without a refusal from the isolation guard; the
  guard refuses git redirected into the main checkout and command shapes it
  cannot parse, not git that stays inside the worktree.
  Evidence: spike, 2026-09-27, in a subagent's own worktree under
  `.claude/worktrees/`: "Preparing worktree (new branch 'sde-spike-1')";
  "Updating 5b180798..6807d03f / Fast-forward"; `git worktree list` clean
  after removal. The spike also deleted a tracked file by `rm -rf
  .doperpowers` — the workspace's parent holds `board.json` — so cleanup is
  `git worktree remove` on the worktree, never a recursive delete on the
  workspace's parent.
- Observation: The harness's Agent-level worktree isolation branches from
  the remote default branch unless `worktree.baseRef` is `"head"`; a
  member dispatched that way would start without the milestones already
  landed.
  Evidence: code.claude.com/docs/en/worktrees, "Choose the base branch"
  (read 2026-09-27); this repository's kept agent worktree
  `agent-a0981e1b519dfbc02` forks from a 2026-08-10 commit of `main`.
- Observation: After EnterWorktree, the shell's persisted working directory
  can stay in the main checkout, and every command is then refused —
  including the `cd` that would move it. ExitWorktree keeping the worktree,
  then EnterWorktree by path, resets it.
  Evidence: three refusals in this session, 2026-09-27 05:2xZ, each
  "this command's working directory resolved to the shared checkout",
  cleared by the exit and re-entry.

## Decision Log

- Decision: verification — the `doperpowers:adversarial-reviewer` agent's
  buildability review on this execution section (more than one milestone);
  the whole-branch review at doperpowers:review-code's high rung; no
  critique debate. The landing table's conflict rows are not exercised by
  this initiative's own run — its members touch disjoint files — and are
  proven by the first group run whose landing rebase reports a resolved
  conflict; that run's report is the evidence. This initiative is the first
  of the two the 2026-09-12 fold's monitoring readout named, and for any
  spec that declares a group the readout adds: wall-clock from the group's
  dispatch to its consumer's dispatch against the sum of the members'
  executor durations; landings that needed a rebase; rebases that carried
  conflicts; re-reviews a rebase caused.
  Rationale: stakes, not size, choose the reviews. The feature is inert
  unless a spec declares a group, so the cost of a wrong call is bounded
  and a critique debate would not pay; the design's riskiest branch is the
  one this run cannot exercise, so the readout carries it.
  Date/Author: 2026-09-27 / fable session; design approved by SSFSKIM in
  brainstorming.

- Decision: the landing phase opens only when every member has returned
  and their decisions are reconciled; a clean verdict is bound to the head
  it covers (`approved <sha7>`) and a rebase records whether it changed
  the patch, so a conflict resolution can never land on an earlier
  approval; the `landed` line is written before any cleanup, and recovery
  recognizes a landing by ancestry; every member ledger line carries its
  `Task N:`; a spec-owned contract is not a member-produced interface
  (group condition 1).
  Rationale: the independent reviews (adversarial design and buildability,
  2026-09-27) showed the first draft promised reconciliation "before
  either lands" while landing members as they came clean, let a recovering
  controller reuse a pre-conflict approval, deleted the recovery branch
  before recording the landing, and declared M1 and M2 as producer and
  consumer of contracts this document itself fixes. Rejected: a
  post-landing repair transition (reopening a landed member through a
  reviewed fix on the execution branch) — more machinery than a barrier
  that costs no wall-clock, since the consumer waits for the last landing
  regardless.
  Date/Author: 2026-09-27 / fable session, review round 1.

- 2026-09-27: execution deferred by SSFSKIM — the spec stays design-only,
  reviewed and committed on branch `worktree-parallel-milestones`, until a
  later session executes it. That session starts at SDE's pre-flight from
  this document (the ledger under `.doperpowers/sde/` holds only this
  session's pre-flight note), with the version bump in M3 taken against
  `main` at that time.

## Outcomes & Retrospective

Pending — written at finish.
