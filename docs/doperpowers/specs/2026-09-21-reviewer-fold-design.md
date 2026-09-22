# The Reviewer fold — the board's review loop as a subagent of the ticket's owner

> **Status:** design approved in-session 2026-09-21 (grill record in the Decision
> Log). Route: spec plus execution plan (doperpowers:writing-plans), executed by a
> `doperpowers:plan-executor` dispatched on sol. Phase 2 of the Architect fold
> (v7.82.0), recorded as open in
> `2026-09-12-one-spec-sized-by-the-gate-design.md`.

## Purpose

Today a ticket on the board changes hands once more than it needs to. The seat
that designed and built it — the Architect with its plan-executor subagent, or
an Executor on a direct ticket — opens the pull request, writes `in-review`, and
ends. A separate Reviewer seat (doperpowers:qa-loops) is then spawned by the
sweep or the PR event, re-orients from zero, runs the review engine, triages,
fixes, and merges. When that review finds a design flaw, the session that holds
the design reasoning is already gone: the ticket goes to `ready-for-architect`
and a fresh Architect re-cuts from nothing. The seat that knew the most about
the work is the one seat the review can never ask.

After this change the review loop runs as a subagent of the seat that owns the
ticket. The owner dispatches `doperpowers:qa-loop` when its PR opens and stays
bound through review. The agent owns everything the Reviewer worker owned —
the engine rounds, the compliance audit, triage, fix waves, grading, the push
chain, the merge, the trail — in its own fresh context. Three things, and only
three, come back to the owner: a finding that conflicts with the spec or plan
text, a finding that is a design gap too big to wave, and a request to dismiss
a non-blocking finding as contradicting design intent. `done` is what ends
the owner's scope.

The first benefit is the lifecycle: one seat per ticket from design to `done`,
one protocol body for the loop, no second seat re-orienting at review, and no
lane hop for a fix that needs the plan's author. The second is expected rather
than measured: a fresh Architect re-cuts from the spec, the pin, the PR, the
trail, and the impasse note, and what the owner holds beyond those is the
orientation already paid and the reasoning that never reached the Decision
Log. The fold makes that available; whether it changes outcomes is something
the smokes and the trail will show.

The independence the loop was built on is kept where it lives: the engine
reviews stateless in fresh worktrees, a non-author triages and grades, the
author never merges its own PR by its own hand or clears a blocker by its own
word, the contract the audit reads is a board-recorded pin the author can
only replace through the board, and every loop the author can drive is
convergence-bounded. What changes is who receives the escalation.

The same change flips the execution tier to sol and retires the `engine:codex`
model route. Every request already goes through one gateway, so a model name is
the whole route; the gateway settings file the codex route pointed at no longer
exists on the machine that runs the board.

Seeing it work: a ticket registered on a board, dispatched to an Architect,
lands as a merged PR with one bound seat for its whole life; `sminos list`
shows that seat through `in-review`; the PR's review-trail comment names the
QA agent's rounds and waves; and a `[trail] dismissal` line on it cites the
spec section the owner named. A second ticket on this repo's API-bound board
does the same after the board service deploys.

## Acceptance

Observable behavior. Commands run from the repository root unless stated.

1. **The agent exists and the skill does not.** `agents/qa-loop.md` has
   frontmatter `model: sol`, `effort: high`, and a `disallowedTools` line
   that names `Skill` and does not name `Agent`. `agents/codex/qa-loop.toml`
   mirrors it and `python3 tests/codex/test-native-agents.py` passes.
   `test -d skills/qa-loops` fails; `ls skills | wc -l` prints 16.
   `grep -rn 'doperpowers:qa-loops' skills agents hooks scripts tests CLAUDE.md README.md`
   returns nothing.
2. **The agent body carries the protocol.** A structural test (the successor
   of `tests/qa-loops/test-skill-entrypoint.sh`, now under `tests/issue-tracker/`)
   asserts the body's sections in order — Role, Orient, Engine, Compliance
   Audit, Join, Triage, Fix Waves, Re-review, Escalate, Scale review,
   Authority, Review Trail — the four triage bins, the three escalation kinds,
   the return contract (`DONE`, `PARKED`, `NEEDS_PANEL`, `ESCALATE`,
   `ENGINE-UNAVAILABLE`), the caps (4 waves, 5 rounds, one closing wave, 45
   minutes), and the dismissal rule (non-blockers only, pointer into the
   pinned spec read and judged, recorded as `dismissed` in the trail, spec
   not edited, escalate only when the spec plausibly speaks to the
   finding), the spec-conflict rule (which-governs or one re-pin), and the
   design-gap convergence rule (a second on the same ticket is the human's).
   It asserts the words
   `Workflow(` and `{{` do not appear in the body: the agent has no Workflow
   tool and no placeholders.
3. **Engine step, single rungs.** The body instructs: at `low`, `medium`,
   `high`, dispatch `doperpowers:reviewer-<rung>` through the Agent tool
   without isolation, the brief `skills/review-code/SKILL.md` gives for a
   single reviewer (base, merge base, head, the diff command) prefixed by the
   location line the review workflow's `repo` argument renders (`The
   repository under review is at <path>: run git with -C <path> and read
   files under that path.`), an optional
   `Lens for this review:` line, and the anti-recursion sentence; read the
   rubric's text result (`## Findings` with `[P0]`–`[P3]` items, `## Verdict`);
   a reviewer that returned no findings but whose verdict names nothing it
   examined is a failed sweep. At `xhigh` and `max`, return `NEEDS_PANEL`
   with `level`, `base`, `baseCommit`, `headCommit`, and the round number,
   and continue only when resumed with a findings file path. The audit is
   written before any reviewer result is opened.
4. **Owner protocols dispatch the agent.**
   `skills/issue-tracker/references/architect-worker-protocol.md`'s Closing
   Artifact section: after `in-review --pr`, dispatch ONE `doperpowers:qa-loop`
   with the brief this spec names, stay bound; on `NEEDS_PANEL` fetch the
   branch, fast-forward the checkout to the requested `headCommit` and verify
   `git rev-parse HEAD` prints it, run
   `Workflow({ scriptPath: "<review-code>/workflows/code-review.js", args: {…, repo: "<that checkout's absolute path>"} })`
   in the background, write the result to a file under the report directory,
   resume the agent with the path; on `ESCALATE` answer per the rule for its
   kind — a spec conflict by which-governs or one re-pin through
   `board-transition.sh <n> in-review "re-pin: …" --plan <path>@<sha>`, a
   design gap by repair-and-rebuild after a fast-forward to origin, a
   follow-up, or a park, and a second design gap on the same ticket by a
   `needs-human` park with both positions; on `PARKED` end the turn with the
   agent's worktree and scratch in
   `implement-worker-protocol.md`'s Closing Artifact section carries the same
   dispatch, with a design-gap escalation answered by `ready-for-architect`
   (the mid-build return, convergence-counted) and no dismissal channel.
   `worker-bootstrap.md` binds `AUTO_MERGE`, `REVIEW_LEVEL`, and
   `TECH_DEBT_ISSUE` for the IMPLEMENT and ARCHITECT roles, rendered and
   validated by `execute-dispatch.sh` on both routes — `REVIEW_LEVEL` refused
   outside `low|medium|high|xhigh|max` before any spawn, `AUTO_MERGE` from
   `AUTO_MERGE_ENABLED`, `TECH_DEBT_ISSUE` from the `tech-debt` label search
   or `none`. `tests/issue-tracker/test-protocol-content.sh` asserts the
   protocol text; `test-execute-dispatch.sh` asserts a rendered prompt carries
   the three bindings and that an invalid floor refuses to dispatch.
5. **The stand-in.** `skills/issue-tracker/scripts/review-dispatch.sh` (moved)
   spawns a seat whose bootstrap
   (`skills/issue-tracker/references/review-standin-bootstrap.md`) binds only:
   `ROLE` (`QAGENT`), `ISSUE_NUMBER`, `ISSUE_URL`, `REPO`, `BOARD_SCRIPTS`,
   `PR_NUMBER`, `PR_URL`, `BASE_REF`, `HEAD_REF`, `HEAD_SHA`, `REVIEW_MODE`,
   `REVIEW_LEVEL`, `REVIEW_CODE_DIR`, `IMPLEMENT_PROTOCOL_FILE`, `AUTO_MERGE`,
   `TECH_DEBT_ISSUE`, `ENV_TRACKER_ISSUE`, `ISSUE_LIST`, `CLOSURE_PACKAGE`,
   `INTEGRATION_REF`, `TICKET_BODY_FILE`, `WORKER_NAME`, and `PROTOCOL_FILE`
   (the dispatcher-pinned path of the stand-in protocol). It binds no
   `BIND_READY_FILE`, `MANIFEST_REF`, `RISK_MANIFEST`, `REPO_FACTS`, or
   `SKILL_FILE`. The stand-in's protocol is: position at the head under
   review, dispatch `doperpowers:qa-loop`, relay `NEEDS_PANEL` (positioning
   the checkout at the requested head first) and `PARKED`, end on `DONE`, and
   end with `ENGINE-UNAVAILABLE` as the last line of its own reply when that
   is what the agent returned; it makes no judgment. Names stay
   `review-pr-<n>`, `review-epic-<n>`, `<ticket>-api-qagent`.
   `pr-review-dispatch.yml` runs the moved path
   `skills/issue-tracker/scripts/review-dispatch.sh`; a structural test asserts
   it, and `review-loop.md` carries the migration note for copies installed in
   adopting repositories.
6. **Owner-first dedupe.** The dispatcher's triggered mode and sweep mode both
   skip a PR whose linked ticket is bound in the seat registry to a live seat
   whose role is not `QAGENT`, printing `#<pr>: owner reviews — skip`, before
   any other dedupe; a ticket bound to a `QAGENT` seat is a stand-in's and
   falls through to the existing registry dedupe, outage streak, and cap.
   Hermetic cases in the moved `test-review-dispatch.sh`: an `in-review`
   ticket bound to a live `12-arch-slug` meta — no spawn; no live owner — the
   stand-in spawns; a finished stand-in whose reply ends `ENGINE-UNAVAILABLE`
   — the existing streak decision runs, not the skip.
7. **Owner recovery in review.** The recover pass of both ticks —
   `board-sweep.sh`'s `pass_recover` and `_sweep_api.sh`'s stall and resume
   phases — covers `in-review`: a ticket bound to an owner seat that is idle,
   not parked, and whose review has no terminal trail verdict, whether the
   latest trail comment carries `ENGINE-UNAVAILABLE` or no trail exists at
   all, is nudged `resume the review of #<pr>` through the sminos CLI once
   per tick, and the third nudge without a new trail comment parks it
   `needs-human` naming the state. Hermetic cases in
   `tests/issue-tracker/test-board-sweep.sh` and the board-api sweep tests
   cover the outage case, the crash-before-dispatch case (`in-review` written,
   no dispatch, no trail), and the cap. The dispatcher's registry-keyed
   outage streak stays for stand-ins.
8. **Model flip.** `agents/plan-executor.md` and `agents/task-executor.md`
   read `model: sol`. `execute-dispatch.sh` and `_sweep_api.sh` pin
   `${IMPLEMENT_MODEL:-sol}` on implement and spike and `${ARCHITECT_MODEL:-fable}`
   on architect; the moved review dispatcher pins `${REVIEW_MODEL:-sol}`.
   `grep -rn -E 'engine:(claude|codex)|WORKER_ENGINE|CLODEX_|T_ENGINE_LABEL|ENGINE_NAME' skills agents scripts tests CLAUDE.md README.md --exclude-dir=sminos --exclude-dir=codex-companion --exclude-dir=review-bench`
   returns nothing. The three exclusions are not the board route: sminos's
   `CLODEX_SETTINGS` is its generic env scrub for any seat, the
   codex-companion tests and fixtures are the separate codex-runtime path
   that stays as it is, and review-bench results are historical logs. (The
   dispatchers keep clearing `DAEMON_CLAUDE_SETTINGS`
   and `DAEMON_CLAUDE_EFFORT` on spawn — an explicit environment for the
   child is defensive and route-neutral; that string is not part of the
   route.) The gate comment
   templates read `[gate] pass — <mode>: <one line>` and the bootstrap
   placeholder tests no longer require `ENGINE_NAME`.
   `tests/issue-tracker/test-execute-dispatch.sh` asserts `[model=sol]` on
   the implement lane and `model=fable` on the architect lane.
   `skills/subagent-driven-execution/SKILL.md`'s Model selection section
   names sol as the executor tier, `model: sonnet` as the cheap override,
   and says no worker runs on fable or astra; its BLOCKED ladder reads
   sonnet → sol → the brief.
9. **Board service.** In `~/Developer/GitHub/arkho/board-service`: (a)
   `in-design → in-progress` is a legal transition for an architect-lane run
   — the build edge PR #136 left open — and `board-transition.sh` no longer
   refuses it under the API binding; (b) `LANE_CROSS` in `src/transitions.js`
   contains neither `in-progress→in-review` nor `in-review→in-progress`; (c) a
   run's write into `in-review` with a numeric `pr` stamps
   `run.package_event_id`, and `in-review → done` is legal for the run that
   owns the ticket (`run.id === tk.owner_run`) in every lane when a leaf's
   `pr_url` is a URL or an epic's `pr_url` equals the run's stamped package —
   a stamped package that differs from the current `pr_url` is refused, with a
   negative test — and the `review-required` refusal applies only when
   `from !== 'in-review'`; (d) `board.decision_park` gains `from_state text`
   written at park time, and the answer relay returns a bound park to
   `from_state` when it is in-flight, falling back to `LANE_INFLIGHT[run.lane]`
   for rows without one; (e) `in-review → in-progress` is convergence-counted
   and its second traversal transmutes to `needs-human` and writes no pin;
   (f) `in-review → in-review` is legal for the owning run with a note and
   requires a `plan` pin (`plan-required` without one); (g) `in-review →
   done` from a run is refused unless a `review-trail` event by that run
   exists after the latest event that entered `in-review` (first entry,
   re-pin, or park return), with a negative test for a trail posted before a
   re-pin; (h) the lane cap counts only open runs whose ticket is in the
   lane's own states, so an architect run holding an `in-review` or
   `in-progress` ticket frees the architect slot; (i) `in-design →
   in-review` is legal for an architect run on an epic (the scale handoff
   the gh binding already carries), refused for a leaf. gh twins in `_board.py`:
   `(in-review, in-progress)` in `EDGE_NOTE_REQUIRED`, the `in-review`
   self-edge in `LEGAL`, `review-trail` among `board-comment.sh --kind`'s
   kinds. `API.md` records all nine. `npm test` in `board-service` passes
   with cases for each; `tests/issue-tracker/test-board-scripts.sh` covers
   the gh twins. The change is merged to arkho `main` and the Render service
   reports the new revision before acceptance 11's second ticket runs.
10. **Records.** Revision Notes are added to
    `2026-07-08-pr-review-loop-design.md`, `2026-07-30-implement-lane-split-design.md`,
    `2026-09-12-one-spec-sized-by-the-gate-design.md`,
    `2026-09-13-qa-loops-native-review-design.md`, and
    `2026-09-09-review-code-lane-design.md`. `CLAUDE.md`'s repo map names the
    agent, the moved references, and 16 skills. `README.md` no longer names
    qa-loops. The version is bumped with `scripts/bump-version.sh` in the same
    PR to the next version above `main`.
11. **Smoke, twice.** (a) On a gh-bound scratch board: a ticket dispatched to
    an Architect reaches `done` with the Architect's seat bound throughout
    (`sminos list` shows it in `in-review`), the trail comment on its PR
    names the QA agent's rounds, a fix wave lands and is re-reviewed at a
    panel level with the owner's checkout positioned at the new head, and a
    `needs-human` park written by the QA agent resumes the Architect and
    reaches the agent with the answer. (b) On the deployed board service under a scratch repo name, after
    acceptance 9 deploys: the same through the API binding, the Architect
    building through the new edge, a fix wave, a `review-trail` event before
    `done`, and no `release` event before `done`. The scratch name isolates
    the smoke from this repository's live queue; the first real ticket here
    follows the merge.
    Outcomes, including failures, are recorded under Surprises & Discoveries.
12. **Suites.** `tests/issue-tracker/run-*.sh`, `tests/claude-code/board-api/*.sh`,
    `tests/sminos/run-sminos-tests.sh`, `tests/codex/test-native-agents.py`,
    and `scripts/lint-shell.sh` pass. A failure that reproduces on `main`
    before this change is recorded, not owned.
13. **Lane caps.** `execute-dispatch.sh` and `_sweep_api.sh` count a seat
    against `ARCHITECT_MAX_CONCURRENT` or `IMPLEMENT_MAX_CONCURRENT` only
    while its ticket is in the lane's ready or in-flight design and build
    states; a hermetic case with one architect seat bound to an `in-review`
    ticket and the cap at 1 asserts a second architect ticket dispatches.
14. **Trail contents.** The agent's trail comment states the review level
    and the auto-merge value it used, the hash of any panel findings file
    the dispatcher handed it, every `dismissed` line with its pointer and
    reasoning, and every re-pin with the delta; the structural test of
    acceptance 2 asserts the body requires each.

## Design

### The qa-loop agent

`agents/qa-loop.md`: `model: sol`, `effort: high`, `disallowedTools: Skill`.
The Agent tool stays — it dispatches reviewers and fixers. Skill is blocked
so no repository instruction can route the agent into a review skill and no
retired skill can be loaded by name.

The body is the Reviewer worker protocol of `skills/qa-loops/SKILL.md`
re-homed, with its dispatcher placeholders replaced by "the brief names" and
these differences:

- **Role.** "You review one pull request for the seat that owns its ticket and
  dispatched you. That seat authored or built the work and answers your
  escalations; it never grades your findings. Your escalation targets are the
  board, the human on their next wake, and — for exactly three kinds — your
  dispatcher." The binding barrier paragraph is gone: there is no registry
  race for a subagent.
- **Workspace.** The agent is dispatched with `isolation: "worktree"`, which
  gives it a worktree of its own — cut at the repository's main checkout
  HEAD, not the dispatcher's (Surprises, Task 11). Its first act is to
  position that worktree at the brief's head: `git fetch origin <head
  branch>` then `git checkout --detach <head>`, and `git rev-parse HEAD` must
  print the brief's `head:`; a head the fetch cannot reach is a park. From
  there the no-ref-switch rule holds: the range it reviews is the brief's,
  and a worktree moved under a live fixer wave loses the wave. The brief
  carries `head branch:` for this and for the push chain.
  It creates one scratch directory with `mktemp -d` outside that worktree
  for wave boards, findings files, and the accepted-commit ledger, and never
  names that path to a fixer. The dispatcher removes the worktree after a
  `DONE` return.
- **Manifests.** It reads `.doperpowers/risk-surfaces.md` and
  `.doperpowers/repo-facts.md` with `git show origin/<base>:<path>` itself.
  The base-ref rule (the PR cannot rewrite what it is audited against) is
  the same; the snapshot the dispatcher used to render is gone.
- **Board writes.** It inherits the owner's session id, so `board-*.sh`
  resolve the owner's run: it writes the trail, tech-debt comments, TOO BIG
  tickets, `needs-human` parks, the merge, and `done`, exactly as the
  Reviewer worker did — but never `ready-for-architect`: a design gap is
  returned to the dispatcher, which writes that edge when it is a stand-in
  or an Executor, and repairs or parks when it is the Architect. Under the API
  binding it writes with the run credentials in its environment.

### The brief and the return contract

The dispatch prompt carries, one line each: mode (`pr` or `scale`); ticket
number and URL, or `none`, and the ticket body file when the bootstrap
delivered one (under the API binding that file is the only route to the
body; `board-show.sh` does not carry it); PR number and URL, or the
closure-package event id and integration ref; base ref and head SHA; the
review level floor (`REVIEW_LEVEL`); the auto-merge flag (`AUTO_MERGE`); the
board scripts directory; the implement protocol path; the tech-debt and
env-tracker issue numbers; a report file path under the ticket's report
directory; and the sentence "your dispatcher answers escalations; return for
them". `REVIEW_LEVEL`, `AUTO_MERGE`, and `TECH_DEBT_ISSUE` are dispatcher-owned
bindings the worker bootstrap now carries for the IMPLEMENT and ARCHITECT
roles, validated by `execute-dispatch.sh` the way the review dispatcher
validated them — a spawned seat cannot inherit them from the dispatcher's
environment. The rest an owner derives from its bindings and `gh pr view`;
the stand-in from its bootstrap. The values relayed through the brief are
the ones the trail states — level and auto-merge — so a relay that lowered
the floor or flipped the switch is visible on the PR.

The agent returns one line first, then at most ten:

- `DONE` — nothing remains local, and: the merge landed and `done` was
  written; or auto-merge is armed on the reviewed head after a bounded wait
  for running checks, and the board's finalize pass writes `done`; or, in
  scale mode, the review was clean and `done` was written on the epic; or a
  ticketless PR was merged. The only return after which the dispatcher
  removes the agent's worktree.
- `PARKED <question>` — every `needs-human` the agent writes: a human-grade
  fork, observation mode, or a cap reached with unaccepted fixes still local;
  and ticketless observation mode, whose park record is the PR comment. A
  board park binds the dispatcher's run, so the answer relay resumes the
  dispatcher; the agent's worktree, scratch directory, and ledger stay in
  place for the resumed agent.
- `NEEDS_PANEL level=<xhigh|max> base=<ref> baseCommit=<sha> headCommit=<sha> round=<n>`.
- `ESCALATE kind=<spec-conflict|design-gap|dismissal> finding=<id> …` with
  the finding, its file and lines, and the agent's position.
- `ENGINE-UNAVAILABLE` — after the retries, the trail outage comment posted.

The dispatcher resumes the agent with `SendMessage` carrying the panel
findings file path, the escalation answer, or the park's answers verbatim.

### The engine step

Level is the highest of the spec's verification rung, the floor, and the size
rule, as today. At `low`, `medium`, and `high` the agent dispatches
`doperpowers:reviewer-<rung>` through the Agent tool without isolation, the
location line naming the agent's own worktree (the shape the review
workflow's `repo` argument renders), the single-reviewer brief from
`skills/review-code/SKILL.md`, the
anti-recursion sentence the workflow adds, and, for lensed extra calls, a
`Lens for this review:` line. It launches the round's calls in the
background, writes the compliance audit, and only then reads their returns.
The result is the rubric's text format; the failure rule reads it: a
reviewer whose `## Verdict` names nothing it examined, or that says it could
not inspect the range, is a failed sweep. At `xhigh` and `max` the agent
returns `NEEDS_PANEL`. The dispatcher fetches the branch and fast-forwards
its own checkout to the requested `headCommit`, verifying `git rev-parse
HEAD` prints it, and passes that checkout's absolute path as the workflow's
`repo` argument: the SHA alone only scopes the diff command, and without
`repo` the workflow isolates every lane at the repository's main checkout
HEAD, not the caller's, so the fast-forward alone positions nothing a lane
reads. With `repo`, the lanes run `git -C` against the dispatcher's checkout
and read its files — after a fix wave the agent's head is ahead of that
checkout until the fast-forward, and a panel run from the old head would
read old files against a new diff. Every head the
agent asks a panel to review is already pushed: a wave pushes before
re-review. The dispatcher then runs the workflow call, saves the result
object to `<report-dir>/findings-r<N>.json`, and resumes the agent with that
path. The `interrupted` verdict reads as a failed sweep, as today.

Re-implementing the panel's deriver, finders, and verifier with Agent calls
inside the agent was rejected: it would duplicate the workflow script and
lose its postcondition-checked verifier.

### Triage and the three escalations

The four bins stay: WAVE (default for every new finding), TOO BIG (new scope:
a ticket), LOG (a stated-reason non-blocker: the tech-debt issue), INVALID
(only by a fixer's evidenced refutation). Three cases leave the agent:

- **spec-conflict** — a finding that conflicts with the pinned spec's or
  plan's own text. The audit's contract is the `plan:` pin at an immutable
  revision; an edit on the branch is divergence evidence, never the
  contract. The owner's answer therefore has two shapes only: *which
  governs* — recorded in the trail, the finding re-bins — or a *re-pin*: the
  owner commits the repaired document on the branch, then mints a new pin
  through the board with a same-state transition,
  `board-transition.sh <n> in-review "re-pin: <delta>" --plan <path>@<newsha>`,
  and the agent re-anchors on the newest pin-minting comment, which the
  audit already treats as the pin in force. One re-pin per review; a second
  is the human's. An Executor owner adjudicates no spec conflict: on a
  pinned plan it writes `ready-for-architect`, on a body-only ticket it
  parks `needs-human`.
- **design-gap** — a TOO BIG whose cause is a design flaw, or the
  seam-clustered impasse at the round cap. An Architect owner answers with
  one of: repair and rebuild — fast-forward the local branch to origin
  first (the agent pushed fixer commits), then `in-review → in-progress`
  with the repaired plan's pin, a plan-executor run, and a fresh `qa-loop`
  dispatch on the new head, the current agent ending; a corrective
  follow-up ticket the agent then LOGs against; or a `needs-human` park. A
  second design-gap on the same ticket is the human's: park with both
  positions. The rebuild edge is convergence-counted in both bindings, so
  the board transmutes a second traversal to `needs-human` by itself. An
  Executor owner writes `ready-for-architect` with the impasse note, as its
  mid-build return does today, and both end. A stand-in seat writes
  `ready-for-architect` on the agent's return.
- **dismissal** — a P2 or P3 finding the agent cannot refute but that the
  spec plausibly speaks to, on a ticket whose `plan:` pin names a spec. The
  agent escalates only when both hold; under-asking costs nothing (the
  finding waves), over-asking hands the author more to wave off. The
  owner's reply carries a pointer into the pinned spec — a section heading
  or a Decision Log entry — and its reasoning. The agent reads the pointed
  section and refuses a pointer that does not speak to the finding's
  subject (a pointer to `## Purpose` dismisses nothing); an accepted reply
  is recorded in the trail as `[trail] dismissed <finding> — <pointer>:
  <reasoning>`, verbatim, and not in the tech-debt sink, whose entries are
  valid deferred work that gardening promotes to tickets. The spec is not
  edited. A P0 or P1 the owner believes wrong is a `needs-human` park with
  both positions. No spec pin, no channel: the finding waves or LOGs as
  today.

### Fix waves and control state

Fixers are the agent's own general-purpose subagents, briefed per
`wave-board.md`, working in the agent's worktree one wave at a time. The wave
board, the `.submitted` snapshot, and the accepted-commit ledger live in the
scratch directory. The bind-ready barrier and its acknowledgement are gone;
the ledger's purpose — detecting an unauthorized writer and gating the push
chain — is unchanged and the grading procedure is unchanged. Caps: four
waves, five engine rounds, one closing wave outside the cap, 45-minute hang
bound.

### The owner's side

**Architect** (`architect-worker-protocol.md`, Closing Artifact): after
registering the executor's residue and writing `in-review --pr --branch`,
dispatch one `doperpowers:qa-loop` and end the turn. Returns arrive as
notifications. `NEEDS_PANEL`: fast-forward the checkout to the requested
head, run the workflow call in the background, save the result object to
the findings file without acting on its contents — the agent reads it, and
records the file's hash in the trail — and resume the agent with the path.
`ESCALATE`: answer per the rule above. `PARKED`: end the turn with the
agent's worktree and scratch in place; `board-answer.sh` returns the ticket
to `in-review` (the `pre-park:` meta already maps it) and resumes this
session, which forwards the answers to the agent. The answers are ticket
content the agent can read itself; the relay is a convenience, so a lost
relay is not a lost answer. `ENGINE-UNAVAILABLE`: end the turn with the
ticket in `in-review`; the sweep's recover pass nudges this session to
re-dispatch. `DONE`: remove the agent's worktree, end. A turn that ends
abnormally anywhere between the `in-review` write and the agent's return
leaves the ticket bound to an idle seat with no verdict in its trail; the
same recover pass nudges it once its activity is older than the stall
threshold, and parks it after three nudges without a new trail comment.
The seat's scope now ends at `done`; the sweep's cancel pass retires it as
an ordinary seat. Authority: "never grade, triage, or merge your own pull
request's review".

**Executor** (`implement-worker-protocol.md`, Closing Artifact): identical
after the PR opens, minus design authority: a design-gap escalation is
answered by `ready-for-architect`, a spec-conflict by `ready-for-architect`
on a pinned plan or `needs-human` on a body-only ticket, and there is no
dismissal channel.

**Lane caps.** A seat counts against its lane's concurrency cap
(`ARCHITECT_MAX_CONCURRENT`, `IMPLEMENT_MAX_CONCURRENT`) only while its
ticket is in the lane's ready or in-flight design and build states; an
owner in `in-review` holds context, not a slot, so the next architect
ticket dispatches while a review runs, as it did when the review was a
separate seat. `execute-dispatch.sh` and `_sweep_api.sh` count by ticket
state, not by open run.

**plan-executor's brief** still says the review loop owns the whole-branch
review; the loop is now the owner's QA agent, and the deferred Minor findings
still reach it through the PR body's `## Unresolved Review Findings`.

### The stand-in seat and the dispatcher

`review-dispatch.sh` moves to `skills/issue-tracker/scripts/` and keeps its
modes (triggered, `--sweep`, scale, API `qagent` claims). Its first dedupe
rule is new: resolve the PR's ticket, and if the seat registry binds that
ticket to a live seat whose role is not `QAGENT`, skip — the owner reviews. A
ticket bound to a `QAGENT` seat is a stand-in's and falls through to the
existing registry dedupe, outage streak, and cap, which read the stand-in's
reply file — so the stand-in ends its reply with its agent's
`ENGINE-UNAVAILABLE` line when that is what came back. The bootstrap shrinks
to the roster in acceptance 5; the manifest snapshots, `SKILL_FILE`, the
control directory, the barrier, and the acknowledgement poll are deleted.
`_spawn_reviewer` keeps the registry bind, the `QAGENT` role stamp, and the
names, so the stale-reviewer sweeps, the outage streak, and the review cap
keep their subject for stand-ins. The stand-in's protocol file,
`review-standin-protocol.md`, is short: fetch and check out the head under
review (a PR head, or the integration ref, or resolve both from the claim
under the API binding), dispatch the agent with the brief, relay
`NEEDS_PANEL` through the Workflow tool from a checkout positioned at the
requested head and `PARKED` through the answer relay, end on `DONE`, and echo
`ENGINE-UNAVAILABLE`. `pr-review-dispatch.yml` moves beside it with its one
command line changed to the dispatcher's new path — a copy installed in an
adopting repository has to be updated by hand, and `review-loop.md` says so —
and `runner-setup.md` moves unchanged.

Ticketless PRs are stand-in reviews; the agent skips board writes when the
brief says `ticket: none`, as the Reviewer worker did.

### The board service (arkho)

Seven changes in `~/Developer/GitHub/arkho/board-service`, one plan task,
with their gh-binding twins in `_board.py` where named:

1. `in-design → in-progress` becomes legal for an architect-lane run: the
   build edge the board's legal-transition table never carried, recorded as
   PR #136's follow-up. Without it the Architect hands off on the API board
   and the one-seat lifecycle this spec promises cannot exist there. The run
   stays open — `in-progress` is not the architect lane's own in-flight
   state, but the ticket is owned, so no lane can claim it — and its parks
   return through change 4. The client's refusal of this edge under the API
   binding (`board-transition.sh`) is removed; the Architect protocol's
   hand-off remains the fallback for any other refusal.
2. `LANE_CROSS` loses `in-progress→in-review` and `in-review→in-progress`.
   The owner's run survives review and its own rebuild. The escalation
   edges stay covered by `SCOPE_END`. An owner that dies is reclaimed by
   lease expiry as today, which clears `owner_run` and lets the `qagent`
   claim's first band pick the ticket up for a stand-in.
3. Terminal-edge authority. A run's write into `in-review` whose `pr` is
   numeric — an epic's closure package — stamps `run.package_event_id`, as a
   qagent claim does today. `in-review → done` is then one rule for every
   lane: the run owns the ticket (`run.id === tk.owner_run`), either the
   leaf's `pr_url` is a URL or the epic's `pr_url` equals the run's stamped
   package, and — change 7 — a review artifact exists. A stamped package
   that differs from the current `pr_url` — a reparent mid-review — is
   refused, so the package match is kept rather than subsumed by ownership.
   `review-required` refuses an implementer run's `done` only from states
   other than `in-review`.
4. `board.decision_park.from_state` (new, `alter table … add column if not
   exists`) is written by the transition into `needs-human`; the answer
   relay returns a bound park to it when it is in-flight, and to
   `LANE_INFLIGHT[run.lane]` otherwise. Without this an Architect's park from
   `in-review` or `in-progress` would resume into `in-design`.
5. `in-review → in-progress` joins the convergence-counted edges — the
   Architect's repair-and-rebuild — with the same transmute of a second
   traversal to `needs-human`. gh twin: the edge joins `EDGE_NOTE_REQUIRED`
   and so `CONVERGENCE_EDGES` in `_board.py`. Under the old design this path
   was the counted `in-review → ready-for-architect`; the fold must not turn
   a counted edge into an uncounted self-loop for the seat with the most
   authorship stake.
6. `in-review → in-review` becomes a legal same-state edge for the owning
   run, note required, carrying `--plan` — the re-pin. gh twin: the self-edge
   joins `LEGAL` in `_board.py`, and `board-transition.sh` accepts `--plan`
   on it and posts the pin-minting comment the audit anchors on.
7. Evidence-gated close. `in-review → done` from a run requires a typed
   `review-trail` event on the ticket, written by that run after the latest
   event that entered `in-review` — the first entry from `in-progress`, a
   re-pin self-edge, or a park return, whichever is newest — so a trail
   posted before a re-pin or a park cannot close the ticket; `board-comment.sh --kind review-trail` is the new
   kind, and the agent posts its trail through it. The server cannot tell
   the QA agent's `done` from the owner's own, but it can refuse a close
   with no review artifact in the log — the same shape as the epic's
   closure-package requirement. Under the gh binding the trail comment is
   posted the same way and no server enforces it.

`API.md` is updated in the lane table, the pick-order note, the terminal
authority paragraph, the convergence list, and the answer route. The task
ends with the change on arkho `main`; the deploy is the human partner's
confirmation before the API smoke.

### Retirement and moves

| from | to |
|---|---|
| `skills/qa-loops/SKILL.md` | `agents/qa-loop.md` (body), `agents/codex/qa-loop.toml` (mirror) |
| `skills/qa-loops/references/wave-board.md` | `skills/issue-tracker/references/wave-board.md` |
| `skills/qa-loops/references/operation-manual.md` | `skills/issue-tracker/references/review-loop.md` |
| `skills/qa-loops/references/review-worker-bootstrap.md` | `skills/issue-tracker/references/review-standin-bootstrap.md` (shrunk) |
| (new) | `skills/issue-tracker/references/review-standin-protocol.md` |
| `skills/qa-loops/references/pr-review-dispatch.yml`, `runner-setup.md` | `skills/issue-tracker/references/` |
| `skills/qa-loops/scripts/review-dispatch.sh` | `skills/issue-tracker/scripts/review-dispatch.sh` |
| `tests/qa-loops/*` | `tests/issue-tracker/` (assertions re-anchored) |

`board-sweep.sh`'s `REVIEW_DISPATCH_CMD` and `_sweep_api.sh`'s `revw` path
follow the move. The issue-tracker SKILL.md's role table gains the QA agent
row and loses the Reviewer Worker row's "daemon" wording; the Repo map row
for `skills/` drops the qa-loops reference and the count.

### Model flip

- `agents/plan-executor.md`, `agents/task-executor.md`: `model: sol`.
- `execute-dispatch.sh`, `_sweep_api.sh`: `${IMPLEMENT_MODEL:-sol}`;
  `${ARCHITECT_MODEL:-fable}` unchanged; the engine-label selector,
  `T_ENGINE_LABEL`, `WORKER_ENGINE`, the codex branch, `CLODEX_*`, and the
  `P_ENGINE_NAME` binding are deleted.
- `review-dispatch.sh`: `${REVIEW_MODEL:-sol}`; the same deletions.
- `worker-bootstrap.md`, `implement-worker-protocol.md`,
  `spike-worker-protocol.md`: `ENGINE_NAME` gone; the gate comment reads
  `[gate] pass — <mode>: <one line>`.
- `sweep-setup.md` knobs: `IMPLEMENT_MODEL | sol`, `REVIEW_MODEL | sol`,
  `WORKER_ENGINE` row removed. Issue-tracker SKILL.md's dispatch ritual step
  2 loses the engine paragraph; `execution-loop.md` loses the engine-label
  line; the architect protocol loses its exemption line.
- `subagent-driven-execution/SKILL.md` Model selection: task-executor on sol
  at high, calibrated to that tier; `model: sonnet` the cheap override; no
  worker on fable or astra; BLOCKED ladder sonnet → sol → the brief.
- `CLAUDE.md` agents row: the pins.
- sminos `--settings`/`--effort` and its gateway-env scrub stay as general
  mechanisms; the dead default path in `gateway_env_keys()` is a follow-on.
- Tests re-anchored: `test-execute-dispatch.sh`, the moved
  `test-review-dispatch.sh`, `test-protocol-content.sh`, the board-api claim
  and resume tests, `run-sminos-tests.sh`'s gateway dimension keeps its
  generic assertions.

### What does not change

The compliance audit and its three classes; the audit-before-findings order;
JOIN; the wave board schema and grading; the caps; the closing wave; the
merge gate and `--match-head-commit`; observation mode; the scale review's
verdict set (`done` or a corrective child); the `confident-ready` state;
`board-answer.sh`; `board-bind.sh`; the GitHub Action's trigger and
permissions (only its command path changes); the review bench under
`tests/review-bench/`.

## Delegated unknowns

Empirical, resolved by acceptance 11 and recorded under Surprises:

1. A `qa-loop` subagent parked by its own `needs-human` write, resumed through
   the owner after `board-answer.sh` — the plan-executor pattern, not yet
   exercised with the park written by the subagent.
2. A fixer committing at depth two inside the agent's isolated worktree, and
   that worktree surviving the agent's return with pushed commits until the
   owner removes it.
3. The sweep's `sminos send` retry nudge landing on an idle owner and the
   owner re-dispatching.

## Decision Log

- Decision: The review loop runs as a subagent of the seat that owns the
  ticket, dispatched after the PR opens; the owner stays bound to `done`.
  Rationale: the review's design-level escalations reach the session that
  holds the reasoning instead of a fresh seat. This reverses the
  2026-07-08 rejection of "resume the implementing daemon for review", whose
  three objections are each answered: author bias — a non-author agent
  triages and grades, the owner only answers three escalation kinds;
  near-compaction context judging — the loop runs in the agent's fresh
  context; PRs with no daemon — the stand-in seat. It narrows the 2026-07-30
  "Architect ends at the plan, never reviews its own PR" to "never grades,
  triages, or merges its own PR's review", and closes the 2026-09-12 "until
  the Reviewer fold" flag.
  Rejected: keep the separate Reviewer seat (the impasse lands on a fresh
  Architect); the owner triages (author bias, and the Architect's context
  holding five rounds and four waves — the load plan-executor was split out
  to avoid).
  Date/Author: 2026-09-21, human partner.
- Decision: The QA agent triages, grades, and merges; the owner adjudicates
  only spec-conflict, design-gap, and dismissal.
  Rationale: triage is rule-bound on purpose (WAVE default, LOG with reason,
  TOO BIG by scope, INVALID by evidence) and a worker tier executes it
  faithfully; what only the owner holds is design intent.
  Rejected: owner merges (the author's hand on its own PR's merge).
  Date/Author: 2026-09-21, human partner.
- Decision: A thin stand-in seat dispatches the agent when no live owner
  exists (owner death, ticketless PR).
  Rationale: one protocol body and one code path; the agent is always a
  subagent; the stand-in has the Workflow tool for panel rounds.
  Rejected: keep the Reviewer worker as a recovery lane (two bodies for one
  loop); no recovery (every owner death costs a wake).
  Date/Author: 2026-09-21, human partner.
- Decision: The Executor seat dispatches the agent for direct tickets too.
  Rationale: one path for both lanes. It authored no design, so a design gap
  returns to `ready-for-architect` as its mid-build return does.
  Rejected: only Architect tickets fold (two dispatch paths).
  Date/Author: 2026-09-21, human partner.
- Decision: Dismissal by the owner is allowed for P2 and P3 only, with a
  pointer into the pinned spec plus reasoning in the reply, recorded verbatim
  by the agent in the trail and tech-debt comment; the spec is not edited;
  the channel exists only on tickets with a spec pin. P0 and P1 the owner
  disputes go to the human.
  Rationale: the loop's rule that the worker never refutes from the finding
  text alone is kept at the worker level; the one agent holding the intent
  gets a bounded, cited channel; blockers stay off the author's word.
  Rejected: always the human (every such finding costs a wake); a
  worker-level dismiss bin (reopens the rationalization failure the loop
  was written against); a Decision Log entry written before citing (the
  human partner chose the lighter form: the trail is the record).
  Date/Author: 2026-09-21, human partner.
- Decision: The agent writes the board as the owner's run.
  Rationale: it is the reviewer role re-homed; the writes resolve to the
  owner's run through the inherited session id, and a park written this way
  binds the owner, which is the resumable session.
  Rejected: the agent returns verdicts and the owner writes (the author's
  hand on the merge-side states).
  Date/Author: 2026-09-21.
- Decision: Single rungs by direct dispatch of the registered reviewer agents
  with text results, pointed at the agent's worktree by the location line
  rather than isolated (isolation would cut them at the main checkout —
  see the 2026-09-22 decision below); the panel handed up as `NEEDS_PANEL`.
  Rationale: subagents have no Workflow tool (probe-verified 2026-09-09 and
  again 2026-09-20) but can dispatch an isolated child (probe 2026-09-20);
  the Agent tool takes no output schema, so the rubric's text is what the
  agent reads, and it triages by reading anyway.
  Rejected: re-implement the panel inside the agent (duplicates the script,
  loses the verifier); the QA agent as a peer seat with Workflow and a return
  address (a listener seat holds no run on the ticket and cannot act on a
  design gap without re-claiming it, so the owner would still be a fresh
  seat at the moment that matters).
  Date/Author: 2026-09-21.
- Decision: Scale review folds too: the recomposing Architect dispatches the
  agent in scale mode; a clean review is `DONE` after the epic's `done`
  write (no merge exists), and a defect returns `ESCALATE kind=design-gap`
  with the corrective child the agent recommends, which the dispatcher
  registers — the Architect per its protocol, a stand-in as today's scale
  verdict did.
  Rationale: the same payoff — the composition's author receives the defect.
  Date/Author: 2026-09-21; return shapes from the execution pre-flight.
- Decision: Both bindings fold; the board service changes so the owner's run
  survives review and may close its ticket, and a park returns to the state
  it interrupted. The server's `review-required` guarantee moves to the
  protocol.
  Rationale: this repo's own board is API-bound; without the change the fold
  would not apply here. The server guard only ever guaranteed a lane hop,
  not that a review happened; the trail and the merge pin carry that.
  Rejected: a child qagent-run route that keeps `done` qagent-only (a
  materially larger server change; recorded as the hardening follow-on if
  the API board ever serves untrusted workers); gh-only now (this repo's
  board would wait).
  Date/Author: 2026-09-21, human partner.
- Decision: Execution defaults to sol — plan-executor, task-executor, the
  implement and spike lanes, the stand-in — and the `engine:*` model route
  retires. Sonnet stays the cheap per-dispatch override; no execution role
  runs astra.
  Rationale: every request goes through one gateway, so `--model` is the
  whole route; `~/.claude/clodex-settings.json` does not exist on the board
  host, so the codex route is dead code; the human partner's routing policy
  already treats sol as the worker tier.
  Rejected: luna as the cheap tier (sonnet is served and already documented);
  keep `engine:codex` as an alias switch (nothing left for it to switch).
  Date/Author: 2026-09-21, human partner.
- Decision: An owner whose review is unfinished is recovered by the recover
  pass of both ticks — nudged while idle without a terminal trail verdict,
  parked after three nudges without progress — whether an outage marker
  exists or not; stand-ins keep the registry-keyed streak.
  Rationale: a subagent has no registry meta, so the name-keyed streak has
  no subject for owner reviews; a crash between the `in-review` write and
  the dispatch leaves no marker at all; and the API tick runs none of the gh
  passes, so a gh-only relay would leave API-owned reviews unrecovered.
  Rejected: a marker-keyed relay in `board-sweep.sh` only (the first draft;
  the adversarial spec review found both gaps).
  Date/Author: 2026-09-21.
- Decision: The qa-loops skill retires; its body is the agent, its references
  live with the other board references under issue-tracker.
  Rationale: nothing invokes the loop by name any more; the dispatcher pins
  a protocol for the stand-in the way it does for every other lane.
  Rejected: keep the skill as the agent's reference (a skill nobody loads).
  Date/Author: 2026-09-21, human partner.
- Decision: Verification for this work: one adversarial spec review
  (`doperpowers:adversarial-reviewer`); a critique debate
  (`doperpowers:critique`) on the independence reversal; the plan's
  adversarial review per doperpowers:writing-plans; branch review at
  `doperpowers:reviewer-high`; the two smokes of acceptance 11.
  Rationale: merge authority and a recorded reversal — the cost of being
  wrong is high.
  Date/Author: 2026-09-21.
- Decision: Route: spec plus execution plan; plan-executor dispatched with
  `model: sol` explicitly.
  Rationale: large, high-stakes, cross-repo; and the flip is dogfooded from
  the first task.
  Date/Author: 2026-09-21, human partner.

- Decision: The board service gains the architect build edge
  (`in-design → in-progress`) as part of this change.
  Rationale: the approved promise — one seat from design to `done` — is
  impossible on the API board without it, since the Architect hands off
  there today; PR #136 recorded the edge as its open follow-up; it is the
  size of the other service changes.
  Rejected: narrow the API smoke to Executor-owned review (leaves the fold
  half-applied on this repo's own board).
  Date/Author: 2026-09-21, from the adversarial spec review.
- Decision: `DONE` means merged; every `needs-human` the agent writes is
  `PARKED` and preserves its worktree, scratch, and ledger.
  Rationale: a cap park keeps unaccepted fixes and the ledger local for the
  resumed review; removing the worktree would destroy them.
  Rejected: the first draft's `DONE` covering cap parks.
  Date/Author: 2026-09-21, from the adversarial spec review.
- Decision: A handed-up panel runs from a dispatcher checkout fast-forwarded
  to the requested head, and the `Workflow` call passes that checkout's
  absolute path as `repo`.
  Rationale: the SHA alone only scopes the diff, so a stale checkout reads
  old files against a new diff; and without `repo` the workflow isolates
  each lane at the repository's main checkout HEAD, not the caller's
  (Surprises, Task 11), so the fast-forward alone positions nothing the
  lanes read. `repo` is the workflow's existing switch for exactly this.
  Date/Author: 2026-09-21, from the adversarial spec review; `repo` added
  2026-09-22 from the gh smoke.
- Decision: The harness's worktree isolation is kept for the QA agent as a
  workspace of its own, and positioning at the reviewed head is the agent's
  own first act; reviewers and the panel are pointed at a path instead of
  isolated.
  Rationale: `isolation: "worktree"` cuts every child at the repository's
  main checkout HEAD (two live drills, two controlled probes, and the plan
  author's own probe, 2026-09-22). The agent's push chain already requires
  its worktree to equal `origin/<head branch>` before any wave, so a fetch
  and detached checkout to the brief's head is the same act one step
  earlier, not a new ref-switch. Reviewers hold no Edit or Write tool, and
  the wave-boundary cleanliness checks catch a stray write; the review
  workflow's `repo` argument already renders the location line and drops
  isolation for exactly this case, so one mechanism serves both rungs.
  Rejected: the owner creating a detached worktree at the head and passing
  its path — it works, but it moves worktree lifecycle into three protocols
  and their tests for a one-line difference in the agent; sharing the
  owner's checkout — fixer waves would mutate the owner's tree under it.
  Date/Author: 2026-09-22, from the gh smoke's BLOCKED return.
- Decision: `REVIEW_LEVEL`, `AUTO_MERGE`, and `TECH_DEBT_ISSUE` become
  worker-bootstrap bindings for the IMPLEMENT and ARCHITECT roles.
  Rationale: a spawned seat cannot inherit the dispatcher's environment, and
  only the review dispatcher validated these; without them the merge kill
  switch and the scrutiny floor would rest on the author's inference.
  Date/Author: 2026-09-21, from the adversarial spec review.
- Decision: The owner-first dedupe skips only for non-`QAGENT` owners; the
  close rule stamps the package on a run's `in-review` write and matches it
  on close in every lane; the ticket body file rides the brief; the Action
  template's command path moves with the dispatcher.
  Rationale: each closes a gap the adversarial spec review found — a stand-in
  is itself a bound seat the streak machinery must reach; ownership alone
  would subsume the package match; the API body exists only in the claim's
  file; the template executed the deleted path.
  Date/Author: 2026-09-21, from the adversarial spec review.

- Decision: The Architect's repair-and-rebuild loop is convergence-bounded:
  `in-review → in-progress` is counted in both bindings and the protocol
  parks a second design gap on the same ticket for the human.
  Rationale: under the old design this path was the counted
  `in-review → ready-for-architect`; the fold must not turn it into an
  uncounted self-loop for the seat with the most authorship stake (the
  2026-07-30 v1.1 rule: two models honestly disagreeing must not produce an
  unbounded relay with no human surface).
  Date/Author: 2026-09-21, from the critique debate.
- Decision: A spec-conflict answer is which-governs or one re-pin through
  the board; a branch edit never changes the audit's contract.
  Rationale: the audit anchors on the immutable `plan:` pin, and the
  2026-07-31 v1.3 decision rejected loosening the head-ref ban because it
  lets the PR self-certify. A same-state `in-review` edge carrying `--plan`
  keeps the contract a board-recorded revision the author can replace only
  visibly, once. The Executor adjudicates no spec conflict.
  Rejected: the first draft's "repairs the document on the branch" (either
  a dead channel or a silent loosening).
  Date/Author: 2026-09-21, from the critique debate.
- Decision: The close is evidence-gated on the API board: `in-review → done`
  from a run requires a `review-trail` event by that run after its
  `in-review` entry.
  Rationale: `review-required` guaranteed the closing actor was a different
  run from the building actor, which the fold removes; this middle — one
  typed kind, one predicate — turns "protocol says a review happened" into
  "the log carries a review artifact or the close is refused". Not proof of
  independence; cheaper than the child-run route the human partner declined.
  Date/Author: 2026-09-21, adopted from the critique's recommendation.
- Decision: Lane caps count by ticket state; an owner in `in-review` holds
  no slot.
  Rationale: `ARCHITECT_MAX_CONCURRENT` defaults to 1, and an owner's run
  now survives review; counting it would serialize every architect ticket
  behind five rounds and four waves of a review sol is running. The seat
  cost the 2026-09-10 and 2026-09-13 decisions weighed is paid in context
  held, not in lane throughput.
  Rejected: raise the default (spends Fable on parallel design to hide a
  counting error).
  Date/Author: 2026-09-21, from the critique debate.
- Decision: At panel levels the owner saves the result without acting on it
  and the agent records its hash in the trail; the floor and the auto-merge
  value the agent used are stated in the trail.
  Rationale: the author is in the data path only where the panel runs and
  where the brief relays dispatcher-owned values; both are made visible on
  the PR rather than prevented. Reading the values from the owner's
  environment instead was rejected: a spawned seat does not inherit the
  dispatcher's environment (`_board_api.py`'s recorded note), so the
  bootstrap binding is the only reliable carrier.
  Date/Author: 2026-09-21, from the critique debate.
- Decision: Dismissals are recorded as `dismissed` in the trail, not in the
  tech-debt sink; the agent reads the pointed section and refuses a pointer
  that does not speak to the finding; it escalates only when the spec
  plausibly speaks to the finding.
  Rationale: LOG means valid and deferred, which gardening promotes to
  tickets; a dismissal means not a defect per intent. A pointer that merely
  resolves is a mechanical check a pointer to `## Purpose` would pass.
  Date/Author: 2026-09-21, from the critique debate.
- Decision: The purpose is framed as a lifecycle simplification first, and
  the escalation-reaches-the-reasoning benefit as expected rather than
  measured.
  Rationale: no instance of a fresh re-cut going badly is on record; the
  fold's costs are concrete and its second benefit is a hypothesis the
  smokes and the trail will test.
  Date/Author: 2026-09-21, from the critique debate.

- Decision: The local lane-cap pre-check and the API tick's review-recovery
  selector read a seat meta key `phase` — `review` while the ticket is in
  `in-review`, `review-parked` after a park from it, restored to `review` by
  the answer relay — stamped by `board-transition.sh` and `board-answer.sh`;
  the gh paths read ticket state directly, and under the API binding the
  server's cap is the authority and counts by ticket state itself.
  Rationale: the API dispatcher and tick read only the seat registry, and a
  ticket read per seat per tick is the cost the registry exists to avoid;
  the transition script already resolves the bound seat for its live-owner
  fence; the server counts every open run today and would hold the slot
  regardless of the client. Recorded from planning and the plan review.
  Date/Author: 2026-09-21.
- Decision: The `phase` key is a candidate filter, not the authority. The
  API tick's review-recovery phase reads each candidate's ticket before it
  acts and proceeds only when the state is `in-review`; a candidate whose
  ticket is `needs-human` is restamped `review-parked` and left alone, and
  any other state clears the key.
  Rationale: the server parks a ticket by itself — the convergence
  transmute and the reconciler's dependency-stall park both write
  `needs-human` with no client transition to stamp the seat — so a local
  `review` can outlive the review. The tick already reads the timeline of
  every candidate; the ticket read is the same cost and removes the case
  where the sweep resumes a parked owner. Recorded from Task 5's review.
  Date/Author: 2026-09-22.
- Decision: The trail's re-pin record is `[trail] re-pin <path>@<sha> —
  <delta>`, beside `[trail] dismissed …`.
  Date/Author: 2026-09-21, from planning.
- Decision: A pre-merge smoke bridges `agents/qa-loop.md` into the installed
  plugin cache's `agents/` directory for its duration, because seats load
  registered agents from the installed plugin, not from the branch worktree;
  the bridge is removed at teardown and recorded in the report.
  Rationale: the plugin installs only from the remote marketplace by version;
  there is no local-checkout install route, and the smoke has to run before
  the version lands on `main`.
  Date/Author: 2026-09-21, from planning.

- Decision: Recovery of an owner in review is bounded by review progress:
  a per-seat `review_recoveries` counter that resets whenever a new
  review-trail artifact appears, separate from the build-time
  `sweep_recoveries`.
  Rationale: acceptance 7 counts nudges without a new trail comment; the
  build counter is lifetime-per-seat and would park a moving review.
  Date/Author: 2026-09-21, from the plan review.
- Decision: Every pin the owner mints — re-pin or rebuild — follows a push,
  and the re-pin reuses the recorded PR and branch; the rebuild and re-pin
  edges are admitted by the plan gates beside the design edges, and a
  convergence transmute writes no pin.
  Rationale: the gh pin gate verifies the sha on the remote; the in-review
  PR gate and the API branch check would otherwise refuse the self-edge.
  Date/Author: 2026-09-21, from the plan review.
- Decision: The recomposition path folds like the PR path: the Architect
  dispatches the agent in scale mode after posting the closure package and
  registers a corrective child itself on a design-gap return; the board
  service gains the epic scale handoff edge it lacked.
  Date/Author: 2026-09-21, from the plan review.

## Surprises & Discoveries

- Observation: A subagent has no Workflow tool but can dispatch a child with
  `isolation: "worktree"`.
  Evidence: probe 2026-09-20 — the parent reported `Workflow: no`; its
  child's `pwd` was `.claude/worktrees/agent-…` on branch
  `worktree-agent-…`, removed after the return.
- Observation: A main session starts on sol through the gateway.
  Evidence: `claude --model sol -p …` answered `sol`, with the harness
  warning `unrecognized_model {"model":"sol"}`.
- Observation: Under the API binding `in-progress→in-review` ends the
  owner's run.
  Evidence: `arkho/board-service/src/transitions.js` `LANE_CROSS` and the
  phase-end block that closes the open run and clears `owner_run`; the
  answer relay returns a bound park to `LANE_INFLIGHT[run.lane]`.
- Observation: The codex route is dead on this machine.
  Evidence: `~/.claude/clodex-settings.json` does not exist; the review
  dispatcher's `P_ENGINE_NAME` exports fill no placeholder.

- Observation: The API board has no `in-design → in-progress` edge; the
  Architect hands off there today.
  Evidence: `board-transition.sh` refuses it under the API binding, and
  arkho's `states.js` has no such row — PR #136's recorded follow-up.
- Observation: The review workflow isolates each reviewer at the caller's
  HEAD; `headCommit` only enters the diff command.
  Evidence: `skills/review-code/workflows/code-review.js` `ISOLATION` and
  the `DIFF` string.

### From the execution (Tasks 1–10)

- Observation: Six of this branch's stops were contradictions inside the
  plan or the spec rather than problems in the code, and each was repaired
  in the document before the executor resumed.
  Evidence: `.doperpowers/sde/2026-09-21-reviewer-fold/progress.md` — who
  writes `ready-for-architect` in stand-in mode (`36999eba`); a return
  contract with no legal outcome for an armed auto-merge, a ticketless
  observation run, or a scale verdict (`f494d11f`); acceptance 8's route
  grep against the dispatcher's own env scrub and then against Task 4's
  scope (`16a5b84b`, `513f46e4`); the phase mark a server-raised park
  leaves stale (`6ec43cd7`); and owner-first on the epic scale path
  (`309db239..b77dfd3d`).
- Observation: A test that compares a database-written timestamp against
  the host clock cannot run on a Postgres inside the Docker Desktop VM.
  Evidence: two VM candidates measured ~70 ms ahead of the host, so
  `board-service`'s `test/mirror-loop.test.js` (`expires_at <= new Date()`)
  failed deterministically and an `nsenter` clock repair did not stick. A
  host-native Postgres 16 on `127.0.0.1:5456` measured ±0.5 ms. It also
  needs `lc_messages = 'C'`: `test/feed-replica.test.js` matches Postgres'
  lock-timeout text in English and this host's locale is Korean.
- Observation: `board-service`'s suite is regression-clean, not all-green.
  Evidence: pristine `origin/main` ran 739 tests, 736 passing, 3 cancelled;
  the branch ran 753/750 with the same three, all in
  `test/mirror-github.test.js` from `AbortSignal.timeout()`'s unref'd timer
  under Node v22.23.2 (`src/mirror/github.js:246`). Two load-sensitive
  drills outside the diff each failed once across nine full runs and were
  left alone.
- Observation: A server guard keyed on an edge's flags does not survive a
  new edge onto the same state — the same forged-close hole reappeared once
  after it was closed.
  Evidence: the epic package stamp was keyed on `require_pr`, which the
  `in-review → in-review` re-pin edge does not carry, so a run could write
  its own `pr_url` and `package_event_id` in one transaction and close a
  scale review it never had. Re-derived from the value instead:
  `to === 'in-review' && isEpic && pr != null`.
- Observation: Renaming the pinned tier to a model name the reader cannot
  place silently disarms the cheap override standing beside it.
  Evidence: 90 fresh single-shot sonnet samples over the SDE Model
  selection text (three batches of 30, inside a 120-call grid whose fourth
  batch was the issue-tracker ritual below). The sentence offering
  `model: sonnet` was byte-identical in both arms; with `opus` named as the
  pinned tier the override was taken 5/5, with `sol` 1/5. Naming the
  relation — "sonnet, the tier below sol" — restored it to 5/5, 14/15
  pooled. A read-back check ("what does this text say?") answers correctly
  every time and cannot detect this; only a control arm can.
- Observation: The dispatch ritual's gateway scrub had never actually been
  emitted.
  Evidence: under the old wording 10/10 unlabelled-or-architect dispatches
  emitted no `DAEMON_CLAUDE_*` prefix at all, so under an ambient gateway
  shell the spawned seat inherited the operator's settings; the
  "ASSIGNMENTS, not omissions" wording produced the explicit scrub 15/15.
- Observation: The seat's `phase` mark is written by client-side
  transitions, so a park the server raises leaves it stale by design.
  Evidence: under the API binding a server-originated park passes through
  no client script, so `phase` stays `review` where a client-driven park
  reads `review-parked`. The lane cap excludes both identically and is
  unaffected; the recovery selector cannot tell them apart from the mark,
  so it verifies the ticket's state before acting and corrects the key
  itself (boundary recorded at plan repair `6ec43cd7`, implemented in
  Task 9).
- Observation: `tests/claude-code/test-subagent-driven-execution.sh` fails
  at a rate on any tree, this branch's or `main`'s, because it regex-matches
  a live session's free text against fixed keyword lists — a correct answer
  in other words is a failure, and which assertion catches it is chance.
  Evidence: three different assertions failed this way during the
  initiative. Task 6, Test 5, on a reply that described reading the diff as
  "verified against the diff, which is the reviewer's actual view of the
  change". Task 10, Test 6 (`executor.*fix\|fix.*issues`, matched per line),
  on a reply that put "findings go back to the executor that wrote the code"
  on one line and "every fix goes through a worker" on another. And on
  `origin/main` unmodified, Test 4 (`Step 1\|beginning\|start\|Load Plan`),
  on a reply that said "the first step of its loop … at setup". Measured
  over the same unchanged suite: one failure in five runs on the branch, one
  in eight on `origin/main`. The section the Task 10 failure probes —
  `skills/subagent-driven-execution/SKILL.md` lines 60–110, the fix loop —
  is byte-identical between the branch and `main`, so nothing on this branch
  reaches it. The test's own header already says it "string-matches its
  verbal explanation against expected keywords". Recorded, not owned;
  tightening it to accept paraphrase, or replacing it with a drill, is debt.
  Run records: `.doperpowers/sde/2026-09-21-reviewer-fold/logs/task-10-{pre,post}-run-skill-tests.log`
  for the full-runner pair, and the eleven isolated reps at
  `/tmp/flake-branch-{1..3}.log` and `/tmp/flake-main-{1..8}.log`.
- Observation: A control that shares a file path with the treatment is not
  a control.
  Evidence: the stand-in eval's first tools-enabled control still bound
  `PROTOCOL_FILE` to this initiative's own protocol, so every control rep
  read the new text and behaved like treatment. Re-rendered from the
  pre-task commit `f0fc00ff` with the retired `qa-loops/SKILL.md` restored:
  control 0/3 correct on a dismissal and 0/3 on a design gap (none wrote
  any board edge), treatment 3/3 on both, touching no board state on the
  dismissal.
- Observation: Owner-first dedupe has two paths; the epic scale path was
  the one the design named only by implication.
  Evidence: the first pass covered the PR path while a live owner's epic
  still fell through to the stand-in's retire and superseded-package logic.
  Closed at `cdb2535d` with one shared `_owner_skip` helper, so the two
  wordings cannot drift apart.
- Observation: "reply and resume the agent" reads as "reply and end the
  turn" to a fair share of readers.
  Evidence: 2/5 first-round samples ended the turn; the line now says the
  turn does not end there (`f70771db`), 5/5 on re-test.
- Observation: An eval gate can pass a cell for structural reasons that
  have nothing to do with the behavior under test — three of them here.
  Evidence: the owner-protocol gate was rewritten three times. It never
  required the `in-review` transition it claimed to check (a spec-conflict
  cell passed having written only `ready-for-architect`); it read only the
  first review dispatch (`qa[0]`), hiding a rebuild's second review whose
  `head:` slot carried prose instead of a sha; and its turn-end criterion
  measured an interval that structurally cannot contain anything. The final
  form gates per review HEAD across the harness's real `system/init` turn
  boundary, drops child events by `parent_tool_use_id`, and counts a board
  write only in shell command position — 10/10 required cells pass at all
  11 heads, the 3 baseline cells fail 3/3.
- Observation: That gate found a protocol defect the structural tests could
  not see.
  Evidence: the scale and recomposition path had never received the "two
  writes, one block" pairing Closing Artifact got, so a treatment seat wrote
  the `in-review` edge and dispatched without the sminos status line beside
  it. Fixed at `4ae0e2e1` with an `assert_order` pin.
  Debt this leaves, both P3 and covered structurally by
  `test-protocol-content.sh`: no tools-enabled cell covers `PARKED` → a
  resumed answer, `ENGINE-UNAVAILABLE` → recovery → a fresh agent, or a
  truthful `DONE` exit (each needs a two-turn `claude -p --resume` cell, or
  a merge route the harness's permission mode will not misread as a merge
  without review); and the scale brief's three lines do not say where
  `closure package:` sits in Closing Artifact's line order, so one seat put
  it after `mode:`.
- Observation: Locking each write orders the writes; it does not order a
  decision taken on an unlocked read.
  Evidence: the API tick's phase repair re-read the ticket inside
  `.metalock`, but its stamp still derived "no difference, write nothing"
  from an unlocked scan — so a repair could stamp `review-parked` over a
  `board-answer`'s freshly committed `in-review`, leaving nothing to
  reclaim the seat as a candidate again. Fixed by moving the whole
  scan-derive-write inside the lock and writing inline; a nested
  `_meta_put` would self-deadlock, flock being per open file description.
- Observation: Progress that was not recorded decides nothing.
  Evidence: when the meta write recording review progress failed, both
  ticks still decided on the unpersisted count in hand, so a review that
  had just posted a round could be parked at the cap on a reset that never
  landed. Reproduced by injecting a directory at the meta writer's tmp path
  — a crashed tick's real leftover — giving `IsADirectoryError` on the gh
  tick and `PermissionError` on the API tick.
- Observation: A concurrency drill can pass for the wrong reason when its
  environment never reaches the code under test.
  Evidence: `DAEMON_HOME=… . "$SCRIPTS/_lib.sh"` — an assignment prefix on
  a special builtin, which POSIX mode does not scope to the command — ran
  the stamp against the suite's own registry, matched no seat, and returned
  instantly, indistinguishable from "the lock held". Fixed by exporting
  inside the subshell; the drill now blocks the repair's re-read on a gate
  file and asserts the answer's call cannot complete inside a two-second
  window while the repair holds the lock.
- Observation: The recovery nudge's wording was not shown to beat a generic
  nudge; the claim was withdrawn.
  Evidence: six sessions in all — two scenarios, each with two treatment
  reps and one control — and on each scenario the control reached the same
  dispatch outcome as the treatment. The original score file had been
  written while a control rep was still running; re-scoring showed that rep
  had in fact dispatched a qa-loop. One control parking the ticket is the
  only difference, and it was not repeated.
- Observation: Six sentences outside the protocol files still named the
  retired Reviewer worker and its lane after the fold, and were read back as
  live doctrine — a stale actor name is a wrong answer, not a stale word.
  Evidence: a fresh-context wording check over the skill's "Who writes the
  board" table and the sweep's knob rows (5 samples per arm, 2026-09-22).
  On the pre-fix text: 5/5 named "the Reviewer worker" as the actor both
  sweep knobs apply to and 2/5 as the merger; on who writes the design-gap
  edge, 5/5 opened on the wrong actor and only 3/5 arrived at the right one,
  two of those reversing themselves mid-sentence. On the corrected text,
  5/5 on all three with no reversal, and the five replies converged on one
  shape where the five before them had produced five.
  `tests/issue-tracker/test-protocol-content.sh` now fences the retired
  names — the worker, the seat, the lane, the daemon, the skill — across
  `skills/issue-tracker/SKILL.md` and `references/*.md`, excepting
  `review-loop.md`'s migration note, which exists to tell an adopting repo
  which retired path to stop calling. The fence is deliberately scoped to
  the prose an agent loads; the board scripts' comments were corrected by
  hand and are not fenced, because `review lane` still means the sweep's
  dispatch pass, the `in-review` state, and the server's `qagent` lane
  there. Harness, prompts and all ten raw replies:
  `.doperpowers/sde/2026-09-21-reviewer-fold/task-10-eval/`.
- Observation: Acceptance 9's code and service behavior is verified; its
  merge-and-deploy clause is not yet satisfied and is Task 12's gate.
  Evidence: arkho PR https://github.com/SSFSKIM/arkho/pull/80 is open at
  review-clean head `36b11fe`, where all nine sub-items pass and `npm test`
  is regression-clean — 753 tests, 750 passing, the same three cancellations
  pristine `origin/main` carries. "merged to arkho `main` and the Render service reports the new
  revision" stands ahead of acceptance 11(b)'s smoke, not ahead of this
  branch's records.

### From the gh smoke (Task 11, acceptance 11a) — the fold does not reach its first engine round

- Observation: `isolation: "worktree"` cuts a child's worktree at the
  REPOSITORY'S MAIN CHECKOUT HEAD, not at the dispatcher's. Not at the
  caller's HEAD, not at the caller's branch, and not changed by the caller
  itself being a harness `--worktree` session. This falsifies the Workspace
  paragraph of "The qa-loop agent" above ("it starts in a fresh worktree at
  the dispatcher's HEAD"), the rationale of the panel-positioning decision
  ("the workflow cuts every reviewer's worktree at the caller's HEAD"), and
  the first half of the earlier observation "The review workflow isolates
  each reviewer at the caller's HEAD" — whose evidence was a code read, never
  a positional probe. The consequence is total: the QA agent's Workspace rule
  correctly refuses to review a range it was not briefed for, so every board
  review parks on its first act, before any engine round or compliance audit.
  The same cut governs the engine's single-rung reviewer dispatches, whose
  `git diff <mb> <head>` still resolves by sha but whose file reads are a
  different revision than the diff.
  Evidence, two live drills and two controlled probes.
  (1) Drill A, the native dispatcher end to end —
  `execute-dispatch.sh 2` under `BOARD_REPO=SSFSKIM/fold-smoke-0922
  LOCAL_REPO=/tmp/fold-smoke AUTO_MERGE_ENABLED=true REVIEW_LEVEL=low
  ARCHITECT_MODEL=fable` — reached `in-review` with PR #5 at
  `525e22fcf679dc9f2e6db9045f9212705e148b3b`, the architect's own worktree at
  that same head, and then: `[board] needs-human: QA checkout mismatch:
  expected 525e22fc… but found c44d61ed…; dispatch a fresh review worktree at
  the expected head`, and `[review-trail] PARKED. Review level low;
  auto-merge on. … Engine rounds none because range identity failed before
  dispatch. Compliance audit not run because this is the wrong range.`
  (2) Drill B, a hand-spawned IMPLEMENT owner at `REVIEW_LEVEL=xhigh`,
  `AUTO_MERGE=off`, whose own worktree was verified at PR #4's head
  `c43beee0d0eafb457221ae64d51f98024b2cb15a`: `[board] needs-human: QA
  worktree mismatch: dispatched head c43beee…, but reviewer worktree is
  c44d61ed…`, and a PR trail reading "Engine rounds: none. Compliance audit:
  not started because the reviewer worktree did not match the pinned range."
  `c44d61ed…` is the scratch repository's `main`.
  (3) Probe from a plain linked worktree at `59dce1e4` (main checkout
  `fe8a4b6d`): the isolated child reported
  `pwd=…/doperpowers/.claude/worktrees/agent-a1d695cc9c96ebbf3`,
  `HEAD=fe8a4b6d` — the main checkout's, under the main checkout's worktree
  root.
  (4) Probe from a `claude --worktree` seat that COMMITTED on its own worktree
  branch: `OWNER_HEAD=c0368a2c56da6725c624f3b4282db2bacdf4a42d`, child
  `HEAD=c44d61ed…` and `ls: probe-marker.txt: No such file or directory`.
  That rules out the branch-switch in Drill B's setup as the cause.
  Full trails: `.doperpowers/sde/2026-09-21-reviewer-fold/task-11-report.md`
  and `logs/task-11-*`. Scratch board kept at
  https://github.com/SSFSKIM/fold-smoke-0922 with both tickets parked and
  resumable.
- Observation: everything in the lane BEFORE the review works on a live gh
  board, so the fold's failure is located precisely at the hand-off it exists
  to create.
  Evidence: on one seat and one binding, ticket #2 ran
  `ready-for-architect` → gate → `in-design` → `in-progress` → `in-review` in
  eight minutes, with `[gate] pass — architect: …` carrying the engine-free
  template of acceptance 8, the architect building through its own
  `doperpowers:plan-executor` on the staged sol pin, and the `in-review`
  transition paired with `sminos status … "reviewing: <PR URL>"` as one block
  — Task 8's ordering, observed live. `sminos list` showed exactly one seat
  bound to #2 throughout; no second seat was ever bound to either ticket. The
  owner relayed the floor and the switch verbatim, and the agent's trail
  stated them back (`Review level: xhigh; auto-merge: off` on #3,
  `Review level low; auto-merge on` on #2), so acceptance 14's relay-visibility
  clause holds on a real PR.
- Observation: a smoke's own fixture can plant a defect in the reviewer's
  diff by accident. `git add -A` in a checkout that hosts
  `.claude/worktrees/` commits a live seat's worktree as a gitlink.
  Evidence: Drill B's first commit carried
  `.claude/worktrees/2-add-a-version-flag-to-hello-sh | 1 +`; removed with
  `git rm --cached` and force-pushed before the review was dispatched.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-09-21: initial version from the brainstorming session.
- 2026-09-21: adversarial spec review (needs-attention, ten findings) applied:
  the API build edge; `PARKED` preserving the workspace; panel positioning at
  the requested head; bootstrap bindings for the floor, auto-merge, and the
  tech-debt issue; per-lane close with package stamping; recover-pass coverage
  of `in-review` on both ticks; the `QAGENT` exemption from owner-first dedupe
  and the stand-in's outage echo; the ticket body file in the brief; the
  Action's command path.
- 2026-09-21: critique debate (`doperpowers:critique`, round one) applied:
  convergence bound on repair-and-rebuild; spec-conflict as which-governs or
  one board re-pin; the evidence-gated close; lane caps by ticket state;
  panel result handling and trail-stated floor; dismissal tightenings and
  the `dismissed` trail record; the purpose reframed; the peer-seat
  rejection's real rationale; fast-forward before rebuild; park answers as
  ticket content.
- 2026-09-21: critique debate converged (round two): the evidence-gated
  close's predicate reads "after the latest event entering `in-review`".
- 2026-09-21: planning (doperpowers:writing-plans) — the stand-in roster gains
  `PROTOCOL_FILE`; the `phase: review` seat meta key, the re-pin trail line,
  and the smoke's plugin-cache bridge recorded as decisions.
- 2026-09-21: plan review (`doperpowers:adversarial-reviewer`, ten findings)
  applied: the server-side lane cap by ticket state; `phase` across parks and
  answers; the pin gates opened for the re-pin and rebuild edges with push
  and reuse rules; the server requiring a plan on the self-edge; the
  recomposition path folded; the relocation frontier kept executable; the
  progress-bounded recovery counter; the smokes rewritten as three drills
  with a full plugin staging and the API drill isolated under a scratch repo
  name.
- 2026-09-21: execution pre-flight — the agent never writes `ready-for-architect`; the dispatcher does (the plan's Task 1 line contradicted Task 7).
- 2026-09-21: Task 1 review — the return contract covers an armed auto-merge, ticketless observation mode, and both scale outcomes.
- 2026-09-21: acceptance 8's grep no longer names `DAEMON_CLAUDE_SETTINGS=`; the dispatchers' explicit clearing stays.
- 2026-09-22: Task 4 review — acceptance 8's grep excludes sminos, codex-companion, and review-bench: none of the three is the board route.
- 2026-09-22: Task 5 review — the API tick's review recovery verifies the ticket's state before it acts; `phase` filters candidates and the server's own parks are corrected there.
- 2026-09-22: Task 7 review — owner-first covers the epic scale path; the stand-in never spawns or rebinds over a live owner.
- 2026-09-22: Task 8 review — the owner's closing turn is three acts in order, and the board write and the sminos status line are one block the scale path carries too.
- 2026-09-22: Task 9 review — a failed progress-reset decides nothing, and the API tick's phase repair derives and writes under one lock.
- 2026-09-22: Task 11 (acceptance 11a) — the gh smoke ran and returned BLOCKED.
  Two live drills and two controlled probes establish that
  `isolation: "worktree"` cuts a child at the repository's main checkout HEAD,
  not the dispatcher's, so the QA agent parks before its first engine round
  every time. Recorded under Surprises; the Design's Workspace paragraph, the
  panel-positioning decision's rationale, and the earlier caller's-HEAD
  observation are contradicted and await the plan author's repair. Everything
  in the lane ahead of the review worked end to end on one bound seat.
- 2026-09-22: Task 10 — the five superseded specs carry their revision note, `CLAUDE.md` names the `qa-loop` agent and `README.md` the fold; the skill and the sweep's knob table name the QA agent and the review stand-in, fenced across `skills/issue-tracker/SKILL.md` and `references/*.md` by `test-protocol-content.sh` over the worker, seat, lane, daemon and skill names alike, outside `review-loop.md`'s migration note. The board scripts' comments lost the retired actor names too, but they are maintainer-facing and carry no fence: `review lane` stays there for the sweep's dispatch pass, the `in-review` state, and the server's `qagent` lane. Surprises from Tasks 1–10 recorded above, fact-checked against the ledger and the task reports.
- 2026-09-22: Task 11 repair — the QA agent positions its isolated worktree at the brief's head itself; single-rung reviewers and the panel are pointed at a path (`repo`), not isolated. Task 13 carries the change; Tasks 11 and 12 re-run after it.
