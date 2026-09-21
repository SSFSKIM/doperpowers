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
   `high`, dispatch `doperpowers:reviewer-<rung>` through the Agent tool with
   `isolation: "worktree"`, the brief `skills/review-code/SKILL.md` gives for a
   single reviewer (base, merge base, head, the diff command), an optional
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
   `Workflow({ scriptPath: "<review-code>/workflows/code-review.js", args: {…} })`
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
   `grep -rn -E 'engine:(claude|codex)|WORKER_ENGINE|CLODEX_|T_ENGINE_LABEL|ENGINE_NAME|DAEMON_CLAUDE_SETTINGS=' skills agents scripts tests CLAUDE.md README.md`
   returns only `tests/sminos/run-sminos-tests.sh` (its generic
   `--settings`/`--effort` dimension) and `skills/sminos/`. The gate comment
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
- **Workspace.** The agent is dispatched with `isolation: "worktree"`, so it
  starts in a fresh worktree at the dispatcher's HEAD — the PR head on the
  ticket branch for an owner, the head the stand-in positioned at otherwise.
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
  tickets, `needs-human` parks, `ready-for-architect` only in stand-in mode,
  the merge, and `done`, exactly as the Reviewer worker did. Under the API
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

- `DONE` — merged and `done` written; nothing remains local. The only return
  after which the dispatcher removes the agent's worktree.
- `PARKED <question>` — every `needs-human` the agent writes: a human-grade
  fork, observation mode, or a cap reached with unaccepted fixes still local.
  The park binds the dispatcher's run, so the answer relay resumes the
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
`doperpowers:reviewer-<rung>` through the Agent tool, `isolation: "worktree"`,
with the single-reviewer brief from `skills/review-code/SKILL.md`, the
anti-recursion sentence the workflow adds, and, for lensed extra calls, a
`Lens for this review:` line. It launches the round's calls in the
background, writes the compliance audit, and only then reads their returns.
The result is the rubric's text format; the failure rule reads it: a
reviewer whose `## Verdict` names nothing it examined, or that says it could
not inspect the range, is a failed sweep. At `xhigh` and `max` the agent
returns `NEEDS_PANEL`. The dispatcher fetches the branch and fast-forwards
its own checkout to the requested `headCommit`, verifying `git rev-parse
HEAD` prints it, because the workflow cuts every reviewer's worktree at the
caller's HEAD and the SHA alone only scopes the diff command — after a fix
wave the agent's head is ahead of the dispatcher's checkout, and a panel run
from the old head would read old files against a new diff. Every head the
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
  mid-build return does today, and both end. A stand-in writes
  `ready-for-architect` itself.
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
  with worktree isolation and text results; the panel handed up as
  `NEEDS_PANEL`.
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
  agent in scale mode; a corrective child returns to it.
  Rationale: the same payoff — the composition's author receives the defect.
  Date/Author: 2026-09-21.
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
  to the requested head.
  Rationale: the workflow cuts reviewer worktrees at the caller's HEAD; the
  SHA alone only scopes the diff, so a stale checkout reads old files against
  a new diff.
  Date/Author: 2026-09-21, from the adversarial spec review.
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
