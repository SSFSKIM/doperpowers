# Fold plan execution into the Architect: one ticket, one session, an executor subagent underneath

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with `skills/execplan/references/PLANS.md` in this repository.


## Purpose / Big Picture


Today a ticket that needs design is worked by two separate background sessions in sequence. An Architect session (frontier model) writes the plan, pins it on the ticket, hands the ticket to the `ready-for-implementer` queue, and ends. Later a dispatcher spawns an Executor session (worker model) that reads the plan from zero context and builds it. When the plan turns out to be genuinely blocked, the Executor pushes the ticket back to `ready-for-architect` and a third session, a fresh Architect with no memory of the design, re-reads everything.

After this change one session owns the ticket from design to pull request. The Architect writes and pins the plan exactly as before, then instead of handing off it dispatches a subagent that executes the plan while the Architect session stays bound to the ticket. If the executor gets stuck, it reports back to the very session that wrote the plan, which still holds the design reasoning and can repair the plan on the spot. The same shape applies to an interactive session after `doperpowers:writing-plans` produces a task-decomposed plan: the session dispatches the executor subagent rather than running the SDE loop in its own context. `doperpowers:execplan`'s Step 3 is deliberately NOT folded — it stays inline (revised 2026-09-10; see the Decision Log).

What you can observe afterwards: `sminos list` shows the Architect seat as `busy` for the whole build, under the status line the Architect set for itself before dispatching (`building: <plan path>`); the ticket moves `ready-for-architect → in-design → in-progress → in-review` under one bound session with no `ready-for-implementer` stop in between; a new registered agent `doperpowers:plan-executor` exists and is what both the board Architect and an interactive session dispatch; and the shell test suites for the board scripts and protocol content pass with new assertions covering the new edge and the new prose.

This is phase 1 of a larger fold ("one ownable ticket = one session"). Folding the Reviewer worker into the same session is deliberately out of scope here, as is renaming the controlled/autonomous tracks.


## Progress


- [x] (2026-09-10) Milestone 1: board schema — the `in-design → in-progress` build edge, plan pin on that edge, architect slot accounting, tests. `test-board-scripts.sh` and `test-execute-dispatch.sh` both green.
- [x] (2026-09-10) Milestone 2: the registered agent `agents/plan-executor.md`, plus its row in the `agents/` cell of CLAUDE.md's Repo map.
- [x] (2026-09-10) Milestone 3: Architect protocol — Build section replaces the handoff; Executor protocol — PLAN-EXECUTION reframed as the recovery path; issue-tracker SKILL.md, sweep-setup.md, execute-dispatch.sh header text. Three protocol-content assertions moved with the prose (see Surprises); `test-protocol-content.sh` green.
- [x] (2026-09-10) Milestone 4: interactive parity — writing-plans handoff, execplan Step 3, subagent-driven-execution controller wording. `doperpowers:using-git-worktrees` does not exist as a skill, so execplan Step 3 keeps the existing `../subagent-driven-execution/isolated-workspace.md` link as the plan directs. The reconciliation grep left one hit to fix: the architect protocol's "repair or re-cut the plan, and hand off again" became "take the build edge again"; the epic-recomposition "ANY exit — handoff, park, verdict" stays, since an epic exit genuinely is one of those.
- [x] (2026-09-10) Milestone 5: protocol-content assertions, all five suites + shellcheck green, version 7.81.0 → 7.82.0, and the live mechanism check — the seat read `busy` for the whole build with its `NOW` column tracking `build: milestone 1/2` → `2/2`, and both commits landed.
- [x] (2026-09-10) Milestone 6 (added after the M5 review): the sweep's stall clock counts subagent transcripts as liveness — `_activity_epoch` in `board-sweep.sh`, both `live` arms of `pass_recover`, and a `test-board-sweep.sh` pair (tickets 73/74) that fails against the parent-only clock and passes against the tree clock.
- [x] (2026-09-10) Fix wave on the whole-branch review's four findings: the API binding refuses the build edge client-side, the build edge yields to an occupied surface (one occupancy rule, shared with the dispatcher), the review audit anchors on whichever comment minted the pin, and the plan-executor carries the repo-facts contract — all under one rule, the handoff is the fallback whenever the build edge is refused. See the Revision Note at the bottom.
- [ ] Final (completed: retrospective written below; whole-branch review run by `doperpowers:reviewer-high`, verdict `incorrect`, its one P1 verified, reproduced, and fixed in Milestone 6; all six checks green afterwards. Remaining: the merge — the implementing session was instructed not to push or open a PR, so integration belongs to the session that owns this branch).


## Surprises & Discoveries


- Observation: a background Claude session whose turn has ended but which still has a background subagent running is reported by the harness as `status: busy, state: working`, and `sminos list` shows it `busy`.
  Evidence (2026-09-10, probe seat `sminos-probe/probe-idle`, session `c2dd43a0`): `sminos reply probe-idle` printed `DISPATCHED` (the turn had ended) while `claude agents --json` printed `{'id': 'c2dd43a0', 'status': 'busy', 'state': 'working'}` and `sminos list` printed `LIVE busy`. This makes the fold safe against ONE of the sweep's two RECOVER arms — the one that resumes an `idle` worker bound to an `in-progress` ticket on the assumption it "finished without a board transition" (`skills/issue-tracker/scripts/board-sweep.sh`, `pass_recover`). A building Architect is never idle in the harness's eyes. **It does NOT make the fold safe against the other arm**; see the M5 review finding below, which is the open blocker on this branch.
- Observation: a subagent can itself dispatch a subagent, and the grandchild can be continued with `SendMessage` from inside the child.
  Evidence (2026-09-10): a general-purpose sonnet subagent reported `agent_tool_available: yes`, `nested_dispatch: ok`, `nested_reply: PONG`, `resume_via_sendmessage: ok (PONG2)`. Depth-2 fan-out (Architect → plan-executor → task executors and reviewers) is therefore available.
- Observation (implementation, M1): widening the architect lane's state tuple alone broke two existing dispatch assertions, because `_slots_used` deliberately falls back to STATE ALONE for a meta carrying no `role` field (a pre-role-write meta). Once `in-progress` is shared by both lanes, that fallback charges one roleless worker to BOTH caps: the fixture's roleless `4-mid-flight-work` meta on an in-progress ticket started occupying the single architect slot and suppressed the unrelated architect dispatch.
  Evidence: `[FAIL] a pre-existing working implement meta occupies its lane's slot … expected to find: 2 / in: 1`. Fixed by making the architect lane require an explicit `ARCHITECT` role on `in-progress` only (every other architect state keeps the roleless fallback); a roleless meta there stays in the implement lane, where it has always been. Both assertions pass again.
- Observation (whole-branch review, M5) — **RESOLVED in Milestone 6; the plan's original safety argument was incomplete**: `pass_recover` has a second arm for `in-progress`/`in-design` tickets that the plan never considered. When `sminos sync` reports the session `live` (which is exactly what a building Architect reports), the sweep falls through to a SILENCE check: it resolves the session's own transcript (`_transcript`, `skills/issue-tracker/scripts/board-sweep.sh:217` — `find ~/.claude/projects -name "<session-uuid>.jsonl"`), and if that file's mtime is `SWEEP_STALL_MINUTES` (default 45) old it calls `_recover` anyway, with reason `silent for <n>m`. `_recover` runs `sminos resume`, and `sminos resume` stops the live turn first (`sminos.py:1814–1885`, `claude_stop` then a bounded wait, refusing to launch if the stop did not take). So a HEALTHY build that runs longer than 45 minutes is killed mid-flight, burns a recovery attempt, and after `SWEEP_RECOVERY_CAP` (3) the ticket is force-parked `needs-human`. Long builds are precisely the architect lane's normal case, so as it stands the fold's headline claim — one session from design to PR — does not hold in production.
  Evidence: the parent transcript receives NOTHING while a subagent runs, and the subagent's own transcript is a sibling the `find` cannot match. From the M5 live-check seat `a48e663c` (dispatch at 23:33:50Z, subagent result at 23:37:32Z):

      sidechain: 0  main: 54
      ('2026-09-09T23:33:50.277Z', 'main')     <- last entry before the dispatch
      ('2026-09-09T23:37:32.542Z', 'main')     <- first entry after the return

  A 3m42s hole in a 4-minute build; at 45 minutes the reaper fires. The subagent's transcript lives under `~/.claude/projects/-private-tmp-fold-live/a48e663c-…/`, a DIRECTORY beside the parent `.jsonl`, so no `-name "<parent-uuid>.jsonl"` search will ever see it. Note also that `sminos status` cannot substitute: it bumps the registry meta, and `pass_recover` deliberately does not use the meta's `updated` ("bumped by the sync just above").
  Resolution (adopted, Milestone 6): the stall clock reads the NEWEST mtime in the session's transcript tree — the parent `<uuid>.jsonl` and anything under a sibling `<uuid>/` directory — so descendant work counts as liveness. Implemented as `_activity_epoch` in `skills/issue-tracker/scripts/board-sweep.sh`, used by both `live` arms of `pass_recover`; `_transcript` is unchanged and still serves the RELAY pass, which selects on `idle` and genuinely wants the parent's turn-end mtime. The alternatives considered and not chosen: raising `SWEEP_STALL_MINUTES` for ARCHITECT-role workers (blunt, still finite), or a status-only clock in the meta (a second timestamp to keep honest).

- Observation (live check, M5): the fold's two load-bearing runtime behaviours both hold, on the substitute dispatch the plan anticipated. A `sonnet` seat spawned with `sminos spawn fold-live … --cwd /tmp/fold-live` dispatched one subagent and ended its turn; `sminos list` reported it `working / busy` for the entire build, and its `NOW` column moved `(empty)` → `build: milestone 1/2` → `build: milestone 2/2` → `build: 2/2 done …` before going `idle`. `git -C /tmp/fold-live log --oneline` then showed `1976a32 world`, `0014b75 hello` on `main`, and `sminos reply fold-live` printed a `status: DONE_WITH_CONCERNS` line in the required shape (status / commit range / tests / residue).
  Evidence: consecutive `sminos list` samples 20s apart —

      fold-live  fold-live  -  working  busy  a48e663c  fold-live  (empty)
      fold-live  fold-live  -  working  busy  a48e663c  fold-live  build: milestone 1/2
      fold-live  fold-live  -  working  busy  a48e663c  fold-live  build: milestone 2/2
      fold-live  fold-live  -  working  idle  a48e663c  fold-live  build: 2/2 done — commits on main; /tmp/fold-l…

- Observation (live check, M5): `doperpowers:plan-executor` did NOT resolve in the spawned seat, and the substitution the plan pre-authorised was used. The installed plugin is a git checkout at `~/.claude/plugins/marketplaces/doperpowers` still on 7.81.0; a seat loads that, not this worktree, so the new agent file is invisible to it until the version ships. The seat fell back to `subagent_type: "general-purpose"` with `model: "opus"` and the agent body pasted into the prompt.
  Evidence: `grep -ho '"subagent_type":"[^"]*"' ~/.claude/projects/-private-tmp-fold-live/*.jsonl` → `1 "subagent_type":"general-purpose"`; `"model":"opus"` on the same dispatch. Agent registration is therefore still unverified end-to-end and is the one acceptance clause this branch cannot prove before install; the mechanism the check exists for (busy-while-building, the status line, a seat dispatching and ending its turn) is proven.
- Observation (live check, M5): the executor created its own git worktree for the scratch repo (`/tmp/fold-live-wt`) even though the brief named the checkout it was dispatched into, which left `/tmp/fold-live`'s working tree pointing at the old commit while `main` carried both new ones. Harmless here (scratch, cleaned up), but it is a real signal for the brief: "work on the branch the brief names, in the checkout you were dispatched into" competes with the executor's own isolation instinct, and a board Architect's brief should say which checkout is authoritative rather than assume.
  Evidence: the returned residue line — `git -C /tmp/fold-live status --short` showed `M PLAN.md` / `D hello.txt` staged after a `DONE_WITH_CONCERNS` return whose commits were nonetheless correct.
- Observation (implementation, M3): three assertions in `tests/issue-tracker/test-protocol-content.sh` had to move with the prose, not just be added to. Two of them the plan anticipated in spirit but scheduled as "pre-existing assertions still pass" for M3: `assert_contains "$arch" "Ends at the plan"` is the exact string the new Role paragraph deletes, and `"a cattle clone fetches the plan's sha from"` is the sentence the verbatim Build section replaces. The third was ALREADY FAILING on `main` before any edit here: it asserts the architect protocol names `doperpowers:codex-companion's \`adversarial-review\` verb`, but both the protocol and `skills/writing-plans/SKILL.md` name the `doperpowers:adversarial-reviewer` agent — the codex verb was retired and the test kept the stale name.
  Evidence: `git stash && tests/issue-tracker/test-protocol-content.sh` → `1 test(s) FAILED`, that assertion alone. Re-pointed at the live mechanism, which is what the assertion's own description asks for ("by its real mechanism").


## Decision Log


- Decision: the execution layer is an in-session subagent, not a second sminos seat.
  Rationale: the goal is one ownable ticket = one session. Durability comes from the artifacts the executor already keeps (the SDE ledger under `.doperpowers/sde/<plan>/progress.md`, an ExecPlan's own `Progress` section) plus the sweep's existing resume ladder on the bound Architect session; visibility comes from the Architect's `sminos status` line. A child seat was considered and rejected by the human partner for this phase.
  Date/Author: 2026-09-10 / design session.
- Decision: one registered agent, `doperpowers:plan-executor`, with the artifact deciding its mode, rather than two agents (SDE manager and ExecPlan executor).
  Rationale: the model and effort pin (`opus`, `high`) and the contract (read the plan, execute, keep the status line current, report in a fixed shape, never write the board) are identical; only two paragraphs differ, and a plan's header already says which kind it is. Fewer names for callers to remember. Not called "executor" because the board already has an Executor Worker.
  Date/Author: 2026-09-10 / design session.
- Decision: the build edge is `in-design → in-progress`, leaf tickets only, and it is the second edge (after `in-design → ready-for-implementer`) allowed to carry `--plan`; on this edge the pin must be a real `<path>@<sha>` (never `pre-spec`) with a branch.
  Rationale: the pin remains what the review loop audits against and what a recovery Executor fetches; `pre-spec` means "no plan, an Executor does it DIRECT", which stays a handoff, not a build. Epics never build (they recompose).
  Date/Author: 2026-09-10 / design session.
- Decision: the Executor worker's PLAN-EXECUTION mode stays as the recovery path and the human's fallback, not the primary path.
  Rationale: when an Architect session dies past the sweep's recovery cap the ticket is parked `needs-human`; the human moves it to `ready-for-implementer` (legal, and the existing pin survives park round-trips), and an Executor resumes from the SDE ledger or the ExecPlan's Progress. No new edge is needed for this.
  Date/Author: 2026-09-10 / design session.
- Decision: the architect lane's slot accounting counts an ARCHITECT-role worker while its ticket is `in-progress` too; the implement lane keeps its role filter so an Architect's in-progress ticket never occupies an implement slot.
  Rationale: `ARCHITECT_MAX_CONCURRENT` is the frontier-spend lever; a building Architect is exactly the spend it meters. The default stays 1 in this change; raising it is an operating decision documented as such.
  Date/Author: 2026-09-10 / design session.
- Decision: the down-shortcircuit (`--plan pre-spec` → `ready-for-implementer`) and the decompose exit are unchanged.
  Rationale: a ticket small enough to need no plan is cheaper on a worker-model Executor and frees the frontier slot; decomposition produces children, not code.
  Date/Author: 2026-09-10 / design session.
- Decision: subagents still never write the board; the plan-executor opens the pull request and returns its URL and residue list, and the Architect makes the board writes (follow-up registration, `in-review --pr`).
  Rationale: one writer per ticket keeps the fence semantics (`board-transition` refuses a mid-turn write from any session but the bound one) and keeps the executor free of board credentials.
  Date/Author: 2026-09-10 / design session.
- Decision: on the now-shared `in-progress` state the architect lane counts only metas whose persisted `role` is literally `ARCHITECT`; the roleless-meta fallback to state alone is kept everywhere else.
  Rationale: the plan says the architect lane counts "an ARCHITECT-role worker" on in-progress, and the implement lane keeps its role filter. The existing fallback (a meta with no role charges whichever lane its ticket's state names) predates the two lanes sharing a state; left alone it double-charges one worker. Narrowing it to the shared state only is the smallest edit that satisfies the plan's stated accounting without weakening the fallback where it still disambiguates.
  Date/Author: 2026-09-10 / implementing session.
- Decision: the sweep's stall clock counts descendant work as liveness — `pass_recover`'s two `live` arms take the newest mtime across the session's transcript tree (the parent `<uuid>.jsonl` plus everything under the sibling `<uuid>/`, where the harness writes `subagents/agent-*.jsonl`), not the parent file alone.
  Rationale: a building Architect's own transcript is silent for the ENTIRE build — its turn ended at the dispatch and the child's stream goes to the sibling directory (observed: a 3m42s hole in a four-minute build, zero sidechain entries in the parent). A parent-only clock therefore reads every healthy delegated build as stalled and reaps it past `SWEEP_STALL_MINUTES`; `_recover` runs `sminos resume`, which stops the live turn first, so the reaper kills the work it was meant to rescue and the recovery cap eventually force-parks the ticket. Long builds are the architect lane's normal case, so without this the fold's headline claim does not hold in production. The meta's `updated` stays out of it for the reason the original code gives: each caller's own `sminos sync` bumps it. The handed-off queue-state arm shares the same clock — a live worker with a working subagent is not silent there either.
  Date/Author: 2026-09-10 / coordinator decision on the M5 review finding, implemented in M6.
- Decision: the wrong-edge `--plan` refusal reads `--plan rides the Architect edges out of in-design only (in-design → ready-for-implementer for a handoff, in-design → in-progress for a build)` — each destination spelled with its source state rather than as a bare arrow.
  Rationale: the plan gives the message text AND requires the substring `in-design → ready-for-implementer` to survive for the existing assertion at `tests/issue-tracker/test-board-scripts.sh`. The plan's literal wording (`→ ready-for-implementer for a handoff`) does not contain it; repeating the source state in each clause satisfies both and reads no worse.
  Date/Author: 2026-09-10 / implementing session.
- Decision (the unifying rule of the fix wave): whenever the build edge is
  REFUSED for a stated reason, the legacy handoff is the fallback — the same
  `--plan` pin on `in-design → ready-for-implementer`, after which the implement
  queue serializes and an Executor runs PLAN-EXECUTION exactly as before.
  Rationale: the fold removed the handoff as the DEFAULT, not as a path. Every
  refusal the build edge can raise (a contested surface, a board whose service
  has no such edge) leaves an Architect holding a finished, pushed, pinned plan;
  without a named exit its only remaining move is a `needs-human` park, which
  spends a human on a queueing problem the board already solves. One rule
  covers every present and future refusal, and the artifact the Architect
  already produced is exactly what the other lane consumes.
  Date/Author: 2026-09-10 / fix wave, from the M5 review findings.
- Decision: the API binding refuses `in-design → in-progress` client-side,
  before any request, and names the handoff in the refusal.
  Rationale: legality on that path is the board service's, and its state table
  (a separate repo) has no such edge — the transition comes back 409 with a
  generic illegal-transition message, and it comes back AFTER the Architect has
  committed and pushed the plan. A client-side refusal is the only place the
  exit can be named. The two mirrored build-edge checks below it are thereby
  unreachable on that path and stay: the day the service's state table gains
  the edge, deleting the refusal is the whole change.
  Date/Author: 2026-09-10 / fix wave.
- Decision: the build edge yields to an occupied surface, under the
  dispatcher's own occupancy rule, moved into `_board.surface_occupant` and
  called by both callers; `SURFACE_OVERRIDE=1` bypasses it on stderr.
  Rationale: the dispatcher deliberately admits an Architect onto an occupied
  surface because design READS — a consolidation ticket has to be designable
  while the surface is busy. Past the build edge the same session writes, with
  no queue between it and the occupant, so the exemption ends exactly there.
  Two copies of an occupancy rule are two rules eventually; one function, two
  call sites, and `execute-dispatch.sh`'s behaviour is unchanged (its tests
  pass unmodified). Gated on a loaded surfaces registry like every other
  surface feature, so a leftover label in a repo whose registry was removed
  cannot fence a build forever.
  Date/Author: 2026-09-10 / fix wave.
- Decision: the review audit's authorization anchor is whichever transition
  comment MINTED the pin — `[board] ready-for-implementer:` for a handoff,
  `[board] in-progress: plan-execution:` for an Architect's build edge — and
  when both exist the later one carries the pin in force.
  Rationale: a real pin means no `[gate] pass` exists, so the audit needs some
  comment to key its drift rules to. The fold created a second minting edge and
  the audit named only the first, which left every Architect-built ticket with
  no anchor at all. The comment strings are what `_board.apply_state` actually
  writes for a non-convergence edge with a note (`[board] <to>: <note>`), and
  the build edge's note is the `plan-execution: <path>@<sha>` line the protocol
  mandates. Both can exist on a ticket that took the handoff after a refused
  build, or that bounced back for a re-cut; the later one is the one in force.
  Date/Author: 2026-09-10 / fix wave.
- Decision: `agents/plan-executor.md` carries the repo-facts contract the
  IMPLEMENT worker has, generalized to any repository that declares
  `.doperpowers/repo-facts.md`.
  Rationale: the executor now does the building an IMPLEMENT worker used to do,
  including the evidence claims a repo's manifest binds, so it needs the same
  contract: bootstrap facts first, validation facts as the commands evidence
  claims must use, evidence add-ons binding the PR body, and a manifest that
  only ever ADDS — a contradiction with the plan is noted, not obeyed.
  Date/Author: 2026-09-10 / fix wave.
- Decision: `doperpowers:execplan`'s Step 3 stays inline — the interactive
  session executes its own ExecPlan.
  Rationale: an ExecPlan is one agent's sequential work, so delegating it in an
  interactive session buys no fan-out and only removes the work from the
  human's view. The board Architect delegates for a reason that does not apply
  interactively: a frontier-model seat should not spend hours building. The
  writing-plans path keeps its dispatch, where the delegated loop really is a
  fan-out the design session should not hold in context.
  Date/Author: 2026-09-10 / human partner, during the fix wave.
- Decision: the plan-executor keeps no progress line of its own, its frontmatter
  description is one sentence, and its ExecPlan contract is stated inline rather
  than by citing `PLANS.md`.
  Rationale: a per-milestone status line is a second progress record to keep
  honest beside the ones that already exist (the SDE ledger, the ExecPlan's own
  `Progress`), and `sminos attach` shows the live session anyway; what the fleet
  view needs is one line saying what the seat is doing, which the dispatching
  session sets once before dispatching. `PLANS.md` is the AUTHORING guide — an
  executor told to follow it is told to follow the wrong document, so the four
  clauses it actually needs are written out.
  Date/Author: 2026-09-10 / human partner, during the fix wave.


## Outcomes & Retrospective


Delivered, on branch `architect-fold` at version 7.82.0, in six commits.

The board now has a build edge. `board-transition.sh <n> in-progress
"plan-execution: <path>@<sha>" --plan <path>@<sha> --branch <b>` succeeds from
`in-design` on a leaf, records the pin, and is refused on an epic, with
`pre-spec`, with no pin, and with no note. `ARCHITECT_MAX_CONCURRENT` now meters
the whole span from `ready-for-architect` through `in-progress`, so the frontier
slot a building Architect holds is charged where the spend actually is. The
Architect protocol's `Ends at the plan` scope is gone: it has a `## Build`
section that takes the edge and dispatches `doperpowers:plan-executor`, and a
`## Closing Artifact` that registers the executor's residue as follow-up tickets
and closes to `in-review` with the PR. The Executor worker keeps PLAN-EXECUTION,
reframed as the recovery lane that resumes from the ledger rather than the top.
Interactively, `writing-plans` and `execplan` both dispatch the same agent
instead of running the execution loop in the design session's own context.

One thing the plan got wrong, and the review caught it. The plan's safety
argument against the sweep covered the arm that resumes an `idle` worker and
missed the arm that reaps a `live` one for transcript silence. A delegated build
is silent in its own transcript by construction — that is the whole point of the
fold — so the parent-only stall clock would have killed every build longer than
45 minutes and eventually force-parked the ticket. Milestone 6 closes it: the
clock now reads the newest mtime across the session's transcript tree, so a
working subagent counts as the session being alive. The lesson generalises past
this branch: when a design deliberately moves work off the path a monitor
watches, every existing liveness check aimed at that path becomes a liveness
check aimed at nothing.

What the change is NOT yet proven to do: resolve `doperpowers:plan-executor` by
name. The live check confirmed the two behaviours the fold rests on — a seat
whose turn has ended but whose subagent is running reads `busy`, and the
executor keeps the operator's status line current — but it had to reach them
through `general-purpose` / `opus` with the agent body pasted, because a spawned
seat loads the installed plugin (7.81.0) and not this worktree. That clause of
Validation and Acceptance can only be exercised after 7.82.0 installs. It is the
one thing to check first on the other side of the merge.

Three lessons worth carrying:

The plan predicted its own test churn imperfectly. It scheduled the
protocol-content assertions for Milestone 5 and expected Milestone 3's prose
edits to leave the existing ones passing; two of them asserted the exact strings
the new prose deletes, so they had to move with the prose rather than after it.
A prose change that a test pins by substring is not additive, and planning it as
additive costs a red checkpoint. A third assertion was already failing on `main`
against a mechanism retired months ago — worth knowing that this suite is not
continuously green, so "the suite passes" needs a baseline run to mean anything.

The slot-accounting change was subtler than one tuple. `_slots_used` falls back
to state alone for a meta with no persisted `role`, which was safe only while no
state belonged to two lanes. Making `in-progress` shared turned that fallback
into a double charge, and the fixture caught it immediately. The general shape:
when two partitions start sharing a key, every "infer the partition from the
key" fallback in the system becomes a bug, and they are easy to miss because
they read as defensive rather than load-bearing.

The executor's isolation instinct fought the brief. Told to work in the checkout
it was dispatched into, it created its own git worktree anyway, which left the
dispatching checkout stale while the commits were correct. Nothing broke here,
but a board Architect's brief should say which checkout is authoritative rather
than assume the instruction lands.


## Context and Orientation


`doperpowers` is a Claude Code plugin made mostly of skills (`skills/<name>/SKILL.md`) and registered agents (`agents/<name>.md`). The board pipeline is the skill `skills/issue-tracker/`: GitHub issues are the ticket board, shell scripts under `skills/issue-tracker/scripts/` are the only writers, and background workers run under protocols that are plain markdown files under `skills/issue-tracker/references/`. A worker is a background Claude Code session spawned through the `sminos` CLI (`skills/sminos/scripts/sminos`), which calls such a session a "seat" and shows it in `sminos list`.

Terms used below:

A **ticket state** is a `status:*` label on an open issue. The states that matter here: `ready-for-architect` (queued for design), `in-design` (an Architect is working), `ready-for-implementer` (queued for execution), `in-progress` (an executor is building), `in-review` (a pull request is open), `needs-human` (parked for the human). The legal transitions are a Python dict `LEGAL` in `skills/issue-tracker/scripts/_board.py` (around line 94); `skills/issue-tracker/scripts/board-transition.sh` refuses anything not in it and adds extra guards of its own.

A **plan pin** is the `plan:` field in the ticket's `board:meta` block (an HTML comment at the end of the issue body). It has the form `<repo-path>@<full-40-hex-sha>` or the literal `pre-spec`. Today `board-transition.sh` accepts `--plan` only on the edge `in-design → ready-for-implementer` (gh binding: around line 405; api binding: around line 200). The `--branch` flag records where the sha is reachable.

The **Architect worker** runs under `skills/issue-tracker/references/architect-worker-protocol.md`. Its "Closing Artifact" section today is: commit and push the plan, then `board-transition.sh <n> ready-for-implementer "<note>" --branch <b> --plan <path>@<sha>`, which ends its scope. The **Executor worker** runs under `skills/issue-tracker/references/implement-worker-protocol.md`; when it finds a `plan:` pin it runs in PLAN-EXECUTION mode (no gate, executes the plan). Both are rendered into a spawn prompt by `skills/issue-tracker/scripts/execute-dispatch.sh`, which also enforces two concurrency caps: `ARCHITECT_MAX_CONCURRENT` (default 1) counted over ARCHITECT-role workers whose ticket is in `ready-for-architect` or `in-design`, and `IMPLEMENT_MAX_CONCURRENT` (default 5) counted over IMPLEMENT/SPIKE-role workers whose ticket is in `ready-for-implementer` or `in-progress` (function `_slots_used`, around line 706).

The **sweep** (`skills/issue-tracker/scripts/board-sweep.sh`) runs on a timer. Its RECOVER pass looks at tickets in `in-progress`/`in-design` with a bound worker and, when that worker is `idle`, resumes it with a nudge ("finished without a board transition"), up to `SWEEP_RECOVERY_CAP` (3) times, then parks the ticket `needs-human`. See Surprises above for why a building Architect is not idle.

**Registered agents** live in `agents/*.md` with YAML frontmatter (`name`, `description`, `model`, `effort`, optional `color`, optional `disallowedTools`) followed by the agent's body prompt. `agents/reviewer-medium.md` is the reference shape. A registered agent is dispatched with the Agent tool as `subagent_type: "doperpowers:<name>"`.

**Two plan artifacts** exist. An ExecPlan (this document is one) is a single self-contained file per `skills/execplan/references/PLANS.md`, executed sequentially by one agent that keeps its `Progress` section current. An implementation plan from `doperpowers:writing-plans` is a task-decomposed file whose header says `REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-execution`; that skill (`skills/subagent-driven-execution/SKILL.md`, "SDE" below) is a controller loop that dispatches one executor subagent per task, a reviewer subagent per task, and keeps a ledger at `<repo>/.doperpowers/sde/<plan-basename>/progress.md`.

**Tests** are shell scripts run directly: `tests/issue-tracker/test-board-scripts.sh` (board transitions against `tests/issue-tracker/mock-gh`), `tests/issue-tracker/test-execute-dispatch.sh`, `tests/issue-tracker/test-board-sweep.sh`, `tests/issue-tracker/test-protocol-content.sh` (asserts strings in the protocol files), and `tests/sminos/run-sminos-tests.sh`. `scripts/lint-shell.sh` is the shellcheck baseline. Versions are bumped with `scripts/bump-version.sh <version>` (never by hand); the current version is read from `.claude-plugin/plugin.json`.

Work in a fresh git worktree off `main` (for example `git worktree add .claude/worktrees/architect-fold -b architect-fold main` from the repository root), and run every command from that worktree's root. Commit after each milestone.


## Plan of Work


### Milestone 1 — the build edge in the board schema

What exists at the end: `board-transition.sh <n> in-progress "plan-execution: <path>@<sha>" --plan <path>@<sha> --branch <b>` succeeds from `in-design` on a leaf ticket and records the pin; it is refused on an epic, refused with `pre-spec`, refused without a branch; the architect lane's slot count includes an ARCHITECT worker whose ticket is `in-progress`.

In `skills/issue-tracker/scripts/_board.py`:

Add `"in-progress"` to `LEGAL["in-design"]` and extend the comment above it: exit is now transition 2/3 (handoff / down-shortcircuit / decompose-epic), the build edge (in-progress, leaf only, real plan pin required — the Architect keeps the binding and executes through `doperpowers:plan-executor`), or a park.

Add `("in-design", "in-progress")` to `EDGE_NOTE_REQUIRED` (the note is the `plan-execution: <path>@<sha>` line, the same words an Executor writes when it enters PLAN-EXECUTION). Do not add it to `CONVERGENCE_EDGES` — it is not an escalation; keep that set's expression as `EDGE_NOTE_REQUIRED - {("in-design", "ready-for-implementer"), ("in-design", "in-progress")}`.

`PRE_PARK["in-progress"]` is already `"in-progress"`, so an Architect that parks `needs-human` mid-build returns to `in-progress` on answer. Nothing to change there.

In `skills/issue-tracker/scripts/board-transition.sh`:

Both bindings currently refuse `--plan` unless `cur == in-design and to == ready-for-implementer`. Change both checks (gh: the `if env["T_PLAN"]:` block around line 405; api: the `_cur`/`$to` check around line 218) to accept either destination `ready-for-implementer` or `in-progress` from `in-design`, and refuse `pre-spec` when the destination is `in-progress` with the message: `--plan pre-spec is the down-shortcircuit — it rides in-design → ready-for-implementer; the build edge (in-design → in-progress) needs a real <path>@<sha> pin`. The existing sha-format check, branch requirement, and remote fetchability check apply unchanged to the build edge. Update the refusal text for a wrong edge to name both: `--plan rides the Architect edges out of in-design only (→ ready-for-implementer for a handoff, → in-progress for a build)`. The existing test at `tests/issue-tracker/test-board-scripts.sh` line ~1317 asserts the string `in-design → ready-for-implementer` appears in that refusal; keep that substring in the new message.

Add a guard beside the E2 epic guard (around line 304): if `cur == "in-design" and to == "in-progress"` then the ticket must not be an epic (`tid in B.epics(tickets)` → die with `in-design → in-progress is the build edge — #<n> is an epic; epics recompose, they never build`), and `env["T_PLAN"]` must be present (die with `the build edge needs --plan <path>@<sha>: the Architect pins the plan before executing it`).

In `skills/issue-tracker/scripts/execute-dispatch.sh`:

In `_slots_used`, change the architect lane's state tuple to `("ready-for-architect", "in-design", "in-progress")`. The role filter already restricts that lane to `ARCHITECT`, and the implement lane's role filter (`IMPLEMENT`, `SPIKE`) already excludes an Architect's in-progress ticket. Update the comment block above the function (around line 700) and the header comment for `ARCHITECT_MAX_CONCURRENT` (around line 32) to say the architect lane's active states are ready-for-architect, in-design, and in-progress while an ARCHITECT holds the binding, because an Architect now builds its own plan.

The surface occupancy check (`_surface_occupant`) already treats `in-progress` as occupied; nothing to change.

Tests, in `tests/issue-tracker/test-board-scripts.sh`, next to the existing plan-pin block (around line 1295): a leaf in `in-design` moves to `in-progress` with a real pin and branch and the body carries `plan: <path>@<sha>`; the same edge with `--plan pre-spec` is refused and the message contains `down-shortcircuit`; the edge without `--plan` is refused and the message contains `needs --plan`; an epic in `in-design` with all children terminal is refused on the edge and the message contains `epics recompose`; a note-less attempt is refused (edge note required). In `tests/issue-tracker/test-execute-dispatch.sh`, find the existing architect-cap assertion and add one: a registry meta with role `ARCHITECT`, status `working`, bound to a ticket in `in-progress` counts toward the architect cap and does not count toward the implement cap. Read the file's existing helpers for how metas and board snapshots are faked before writing the case.

### Milestone 2 — the registered agent

Create `agents/plan-executor.md` with exactly this content (frontmatter and body):

    ---
    name: plan-executor
    description: Executes a pinned plan on behalf of the session that authored it — an ExecPlan sequentially, or a task-decomposed implementation plan by running doperpowers:subagent-driven-execution and dispatching its task executors and reviewers. Opens the pull request; never writes the board.
    model: opus
    effort: high
    color: green
    ---

    You execute a plan another session wrote and still owns. That session is
    bound to the ticket, holds the design reasoning, and is where every
    escalation goes; you are its hands. The dispatching brief names the plan
    file, the spec it argues from (if any), the branch to work on, the seat
    alias to report progress under, and the report file to write.

    ## Mode

    Open the plan first. If its header names `doperpowers:subagent-driven-execution`
    as the required sub-skill, invoke that skill and follow it: you are its
    controller — fresh executor per task, review at each dependency frontier,
    fixes resumed on the executor, the final whole-branch review, the ledger.
    Otherwise the file is an ExecPlan: follow the implementing contract in
    `skills/execplan/references/PLANS.md` — proceed milestone by milestone
    without asking for next steps, resolve ambiguities the plan already
    settles from the plan, keep its `Progress`, `Surprises & Discoveries`, and
    `Decision Log` sections current at every stopping point, commit frequently.

    Either way, work on the branch the brief names, in the checkout you were
    dispatched into. Test-driven development applies to testable logic.

    ## Progress line

    Keep the seat's status line current when the brief gives you an alias:
    `sminos status <alias> "build: task 3/7 — <one line>"` (SDE) or
    `"build: milestone 2/4 — <one line>"` (ExecPlan), updated when a task or
    milestone completes and when you block. This is the only progress the
    operator sees without attaching; a stale line reads as a stalled build.

    ## Escalation

    Return to the dispatching session — do not build past it — when the plan is
    genuinely blocked (wrong about the codebase in a way you cannot absorb, not
    merely divergent), when a finding conflicts with the plan's own text, or
    when a fork needs a decision the plan does not settle. Commit WIP first.
    Your return states the blocker, the exact plan text at issue, what you
    tried, and your recommended resolution; the dispatching session repairs the
    plan or answers and continues you with the answer. Divergence you can
    absorb is absorbed and recorded in the plan's living sections, not
    escalated.

    ## Closing

    When the plan is complete and the final review is clean, open the pull
    request yourself, ready for review (draft only if the work genuinely is not
    reviewable yet). The body carries `Closes #<ticket>` when the brief names a
    ticket, a `## Validation Evidence` section with each claim of done and the
    command and output that back it, a `## Confusions` section only if
    something was genuinely confusing, and a `## Residue` section listing work
    you left behind that deserves its own ticket, each item with two or three
    lines of context — you do not register tickets; the dispatching session
    does, from this list.

    ## Report

    Write the full account to the report file the brief names. Return only:
    status (`DONE`, `DONE_WITH_CONCERNS`, `BLOCKED`), the PR URL when opened,
    the commit range, a one-line test summary, and the residue list or
    `residue: none`. Everything else is in the report file.

    You never write the board: no `board-*.sh` calls, no `gh issue edit`.
    Environmental friction you routed around goes in the report; friction that
    blocked you is a `BLOCKED` return.

(Revised 2026-09-10: the shipped body diverges from the text above — the `## Progress line` section is gone, the frontmatter `description` is one sentence, the ExecPlan contract is stated inline instead of citing `PLANS.md`, and a `## Repo facts` section carries the IMPLEMENT worker's manifest contract. `agents/plan-executor.md` is the artifact; see the Decision Log.)

Add a row for it to the `agents/` entry of the Repo map table in `CLAUDE.md` (the project root), after the reviewer rungs: `plan-executor` (opus/high) executes a pinned plan for the session that authored it — SDE controller for a task-decomposed plan, sequential for an ExecPlan; dispatched by the board Architect and by writing-plans / execplan in an interactive session.

### Milestone 3 — the Architect builds; the Executor is the fallback

In `skills/issue-tracker/references/architect-worker-protocol.md`:

Rewrite the `## Role` paragraph's second sentence. Replace "Your scope **Ends at the plan**: you write no implementation code, and you never review the Executor's output — the review loop (doperpowers:qa-loops) owns that, and no orchestrator-judge exists in this pipeline." with:

    Your scope runs from the ticket to the pull request: you author the plan,
    then execute it through a `doperpowers:plan-executor` subagent while you
    stay bound to the ticket, so a blocked plan comes back to the session
    that wrote it rather than to a fresh Architect. You write no
    implementation code yourself, and you never review the pull request —
    the review loop (doperpowers:qa-loops) owns that, and no
    orchestrator-judge exists in this pipeline.

Replace the whole `## Closing Artifact` section with a `## Build` section and a `## Closing Artifact` section:

    ## Build

    The plan is the ENTIRE interface to its executor — self-contained for a
    zero-context reader; nothing you learned survives except what the plan
    and the ticket carry. Commit the plan on the ticket branch and PUSH it
    (recovery depends on origin-visible artifacts), then take the build edge
    in one transition:

    {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-progress "plan-execution: <repo-path>@<full-commit-sha>" --branch <branch> --plan <repo-path>@<full-commit-sha>

    The `plan:` pin is machine-read — it names the immutable revision the
    review loop audits against (your executor's living-plan updates on the
    branch are divergence evidence, not the contract) and the revision a
    recovery Executor fetches if this session is lost. `--branch` is not
    optional beside a pin.

    Then dispatch ONE `doperpowers:plan-executor` subagent (the Agent tool,
    `subagent_type: "doperpowers:plan-executor"`; its model and effort are
    pinned in its definition). The brief carries: the plan path and, for a
    spec-shaped plan, the spec path; the ticket number and URL; the branch;
    your seat alias (`{{ROLE}}`-lane seats are named `<n>-<slug>`; `sminos
    list` shows yours) so it can keep your status line current; and a report
    file path under the plan's directory. An ExecPlan-shaped plan runs
    sequentially; a spec-shaped plan makes it the SDE controller, which
    dispatches its own task executors and reviewers — depth-2 fan-out is
    available and verified.

    While it runs your session is busy in the harness's eyes even though
    your turn has ended, so the sweep leaves you alone; its completion or
    escalation arrives as a notification that starts your next turn.

    On a `BLOCKED` return: the executor names the plan text at issue and a
    recommended resolution. If the fork is yours (design, agent-answerable),
    repair the plan on the branch, commit, and continue the same subagent
    with SendMessage — it holds the build context and skips a fresh
    orientation. If the fork is the human's, park from in-progress
    (`needs-human`, the numbered-questions format, WIP already committed by
    the executor) and, when board-answer resumes you, relay the answers to
    the same subagent. A second `BLOCKED` on the same plan text after your
    repair is the human's: park with both positions stated.

    ## Closing Artifact

    On `DONE` (or `DONE_WITH_CONCERNS` whose concerns you have read and
    dispositioned): register every item of the executor's residue list as a
    follow-up ticket (`--spawned-by {{ISSUE_NUMBER}}`, body authored from the
    residue context, per the issue-tracker ticket contract) — a follow-up
    not registered does not exist — then close your scope:

    {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-review "<one-line>" --pr <PR URL> --branch <branch>

    From the PR on, the review loop owns the path to merge. This transition
    ends your scope and releases your binding.

    The down-shortcircuit and the decompose exits above are unchanged: a
    ticket whose pre-spec suffices goes to `ready-for-implementer` with
    `--plan pre-spec` for an Executor worker, and an epic's children are
    registered, never built here.

In `## Authority`, replace "NEVER: implementation code, plan execution, terminal states (the ONE exception is a recomposition verdict on your own epic, below), other tickets' states, reviewing the Executor's output." with "NEVER: implementation code in your own hands (your plan-executor writes it), terminal states (the ONE exception is a recomposition verdict on your own epic, below), other tickets' states, reviewing your own pull request."

In `## If Resumed With Answers`, append one sentence: "If a plan-executor subagent was in flight when you parked, the answers go to it next: continue it with SendMessage carrying the answers verbatim."

In `skills/issue-tracker/references/implement-worker-protocol.md`:

In `## Mode Selection`, change the PLAN-EXECUTION bullet's opening to: "`plan: <path>@<sha>` → **PLAN-EXECUTION**: an Architect authored your plan at that immutable revision on the recorded branch and, in the normal course, executed it itself through its plan-executor subagent. You are here because that session was lost (the sweep's recovery cap ran out and the human returned the ticket to this lane) or because a human chose this lane: pick up from where the work actually stands — an SDE ledger at `.doperpowers/sde/<plan-basename>/progress.md` on the branch, or the ExecPlan's own `Progress` section — never from the top. NO intake gate — the Architect's phase carried the quality machinery; you do not re-run the gate or re-judge the design."

In `skills/issue-tracker/SKILL.md`:

In the "Who writes the board" table, the Architect Worker row's "writes" cell becomes: "its OWN ticket's open states through design and build (`in-design`, the build edge to `in-progress` with the `plan:` pin, `in-review` with the PR); NEW child/follow-up tickets; on an EPIC, the recomposition verdict — including that epic's terminal states, the one scoped exception to terminal authority". The Executor Worker row's "writes" cell gains at the end: " — DIRECT tickets, and PLAN-EXECUTION as the recovery lane for a plan whose Architect session was lost".

In "State vocabulary", the `in-design` row's meaning becomes: "the Architect's in-flight design state — gate passed, grill/authoring underway; exits to `in-progress` (the build edge: plan pinned, the Architect executes it through its plan-executor subagent and stays bound), to `ready-for-implementer` (down-shortcircuit or decompose), or to a park (`pre-park:` returns here). On an epic it also exits to `done`/`in-review` — the recomposition verdict; on a leaf those edges are refused". The `in-progress` row's meaning becomes: "a bound session is building it — an Architect past the build edge, or an Executor past its gate (an executor-queued or `needs-info`-released epic is pulled here and stays while children run; the architect queue pulls to `in-design` instead, and the other three parks are never pulled)". The happy path sentence at the top of that section becomes: "The architect lane's happy path is `ready-for-architect → in-design → in-progress → in-review → done`, one bound session from design to PR; a direct ticket starts at `ready-for-implementer` and an Executor takes it `in-progress → in-review`."

In "The dispatch ritual", step 4's last sentence lists the worker's first board write; leave it, and add: "An Architect's later writes on the same binding are the build edge (`in-progress`, plan pinned) and `in-review` with the PR — one session end to end; `ARCHITECT_MAX_CONCURRENT` meters that whole span."

In "The wake ritual", step 2's `needs-human` fallback paragraph gains one sentence after "the next dispatch runs the lane's protocol against the enriched ticket from fresh context": "A ticket parked by the sweep's recovery cap while its Architect was mid-build keeps its `plan:` pin across the park: `board-transition.sh <n> ready-for-implementer` hands it to an Executor in PLAN-EXECUTION, which resumes from the ledger on the branch."

In `skills/issue-tracker/references/sweep-setup.md`, the `ARCHITECT_MAX_CONCURRENT` row's meaning becomes: "architect-lane slot cap — the Fable-spend lever; counted over ARCHITECT-role workers from `ready-for-architect` through `in-progress` (an Architect executes its own plan), separate from the implement cap. The default 1 now spans design plus build; raise it when queued design work waits on a long build."

### Milestone 4 — interactive parity

In `skills/writing-plans/SKILL.md`, replace the last block of `## Execution Handoff` ("Then execute: - REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-execution - Fresh executor per task; reviews at dependency frontiers; fixes resume the executor") with:

    Then dispatch execution rather than running it here: one
    `doperpowers:plan-executor` subagent (Agent tool, `subagent_type:
    "doperpowers:plan-executor"`), briefed with the plan path, the spec path,
    the branch, and a report file path under the plan's directory. It reads
    the header, invokes doperpowers:subagent-driven-execution, and runs that
    loop — fresh executor per task, reviews at dependency frontiers, fixes
    resuming the executor — in its own context, so yours stays the design
    session. It returns on completion (with the PR URL) or on a `BLOCKED`
    that names the plan text at issue: repair the plan or answer, then
    continue the same subagent with SendMessage; a fork that is your human
    partner's, put to them first. Running the loop in this session remains
    available when you want to watch every dispatch.

Leave the plan header text (`REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-execution`) exactly as it is: the plan-executor keys its mode off that line.

In `skills/execplan/SKILL.md` — REVISED 2026-09-10, and reverted in the fix wave: `## Step 3 — Execute` stays exactly as it is on `main`. An ExecPlan is one agent's sequential work, so an interactive session that delegates it buys no fan-out and only loses sight of the work; the daemon Architect delegates for a different reason (a frontier-model seat should not spend hours building). The superseded instruction, for the record, was to replace that step with:

    ## Step 3 — Execute

    Dispatch one `doperpowers:plan-executor` subagent (Agent tool,
    `subagent_type: "doperpowers:plan-executor"`) with the ExecPlan's path,
    the branch of an isolated workspace (doperpowers:using-git-worktrees —
    create it first), and a report file path. It follows PLANS.md's
    implementing contract: no prompts for next steps, ambiguities resolved
    from the plan, `Progress`, `Surprises & Discoveries`, and the `Decision
    Log` kept current, frequent commits. It returns `DONE` with the branch
    ready for the exit gate, or `BLOCKED` naming the plan text it cannot
    absorb — revise the plan (the grill already exhausted the human-grade
    questions; a new one goes to your human partner), then continue the same
    subagent with SendMessage. Executing the plan in this session yourself is
    the fallback when no subagent can be dispatched.

    This profile fits durable background sessions — seats spawned through
    doperpowers:sminos: the ExecPlan is exactly what a spawn prompt can
    carry, and it survives the seat's context death — the document is the
    memory.

If `doperpowers:using-git-worktrees` does not exist as a skill in `skills/` (check `ls skills/`), reference `skills/subagent-driven-execution/isolated-workspace.md` instead, as the current text does.

In `skills/subagent-driven-execution/SKILL.md`:

In `## Model selection`, replace "Never dispatch workers on the top tier (fable): it adds cost without adding reliability and is the controller's tier, not the worker's — the plan and the brief absorb the difficulty, not the model." with "Never dispatch workers on the top tier (fable): it adds cost without adding reliability — the plan and the brief absorb the difficulty, not the model. The controller itself is normally `doperpowers:plan-executor` (opus, high), dispatched by the session that wrote the plan; that session is one hop up for anything the controller cannot settle."

In step 2 (Pre-flight), replace "Present findings to your human partner as one batched question — each beside the plan text that mandates it — before execution; a clean scan proceeds without comment." with "Present findings as one batched question — each beside the plan text that mandates it — to whoever dispatched you (the plan's author session, or your human partner when you are running the loop yourself) before execution; a clean scan proceeds without comment."

In `## Dispatch hygiene`, replace "A finding that conflicts with the plan's own text is the human's decision: present the finding and the plan text, ask which governs." with "A finding that conflicts with the plan's own text is the plan author's decision: return it with the finding and the plan text and ask which governs — the author session repairs the plan or escalates to your human partner."

In `## Executor statuses`, the BLOCKED bullet's "plan wrong (escalate to the human)" becomes "plan wrong (return to the session that dispatched you, or to the human when that is you)".

Search the four edited skill files and the two protocols for any remaining sentence that assumes the SDE loop runs in the human's own session or that the Architect ends at the handoff (`grep -n "hand off\|handoff\|Ends at the plan\|your human partner" skills/subagent-driven-execution/SKILL.md skills/writing-plans/SKILL.md skills/execplan/SKILL.md skills/issue-tracker/references/architect-worker-protocol.md`) and reconcile each hit with the new shape; the "your human partner" voice stays wherever the human genuinely is the addressee.

### Milestone 5 — tests, lint, version, live check

In `tests/issue-tracker/test-protocol-content.sh`, in the architect-protocol block (around line 233), add assertions: the architect protocol contains `plan-executor`, contains `in-progress "plan-execution:`, contains `## Build`, and does not contain `Ends at the plan`. In the executor-protocol block, add: the executor protocol contains `recovery` near PLAN-EXECUTION (assert the substring `resumes from` or the exact phrase you wrote). Add an assertion that `agents/plan-executor.md` exists, has `model: opus` and `effort: high`, and contains `never write the board`.

Run, from the worktree root:

    tests/issue-tracker/test-board-scripts.sh
    tests/issue-tracker/test-execute-dispatch.sh
    tests/issue-tracker/test-board-sweep.sh
    tests/issue-tracker/test-protocol-content.sh
    tests/sminos/run-sminos-tests.sh
    scripts/lint-shell.sh

All must pass. Then bump the version: read the current one from `.claude-plugin/plugin.json`, add one to the minor number (7.81.0 → 7.82.0 if nothing else landed meanwhile; use whatever is current plus one minor), and run `scripts/bump-version.sh <new>`. Commit the bump with the milestone.

Live mechanism check (no board involved): create a scratch git repository under `/tmp/fold-live/` with one file and a two-milestone ExecPlan at `/tmp/fold-live/PLAN.md` whose milestones are "create `hello.txt` containing `hello`, commit" and "append a line `world`, commit". (The check as run also had the executor write a per-milestone `sminos status` line, which is how the `NOW` column moves in the record below; that per-milestone line is no longer part of the contract — the dispatching session sets its own status once and progress lives in the plan's `Progress` section.) Spawn a seat as the fold would: `skills/sminos/scripts/sminos spawn fold-live "<prompt>" --cwd /tmp/fold-live --model sonnet` where the prompt says: register nothing, dispatch one `doperpowers:plan-executor` subagent with the plan path `/tmp/fold-live/PLAN.md`, branch `main`, alias `fold-live`, report file `/tmp/fold-live/report.md`; end the turn after dispatching; on the completion notification reply with the returned status line. Then observe with `sminos list` that the seat is `busy` while the build runs and its `NOW` column changes to `build: milestone 1/2` then `2/2`; that `sminos reply fold-live` eventually prints a `DONE` line; and that `git -C /tmp/fold-live log --oneline` shows the two commits. Retire the seat with `sminos retire fold-live --purge` afterwards. Record the observed `sminos list` lines under Artifacts and Notes. Note: the registered agent is only visible to that seat if the plugin the seat loads is this checkout (a dev marketplace install pointing at the worktree, or the plugin cache already carrying the new version). If the seat cannot resolve `doperpowers:plan-executor`, run the same check with `subagent_type: "general-purpose"` and `model: opus` and the agent body pasted as the prompt's first section, and record that substitution here as a Surprise — the mechanism under test is the busy-while-building and status-line behaviour, not agent registration.


## Concrete Steps


From the repository root on `main`:

    git fetch -q origin main
    git worktree add .claude/worktrees/architect-fold -b architect-fold origin/main
    cd .claude/worktrees/architect-fold

Milestone 1 edits, then:

    tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -3
    tests/issue-tracker/test-execute-dispatch.sh 2>&1 | tail -3
    git add -A && git commit -m "board: in-design → in-progress build edge carries the plan pin; architect slots span the build"

Milestone 2, then `git add agents/plan-executor.md CLAUDE.md && git commit -m "agents: plan-executor — executes a pinned plan for the session that authored it"`.

Milestone 3, then `tests/issue-tracker/test-protocol-content.sh 2>&1 | tail -3` (expect the pre-existing assertions still pass; new ones come in Milestone 5) and commit `"issue-tracker: the Architect builds its own plan through plan-executor; PLAN-EXECUTION is the recovery lane"`.

Milestone 4, then commit `"skills: writing-plans and execplan dispatch plan-executor; SDE controller wording"`.

Milestone 5: add assertions, run the six commands listed there, bump the version, commit `"tests + version: architect-executor fold; <new version>"`, then the live check.

Expected tail of a passing shell test run is a line like `PASS: N assertions` or `N passed, 0 failed` — read the file's own summary format; any `FAIL` line is a failure.


## Validation and Acceptance


After the change, on a board with the gh binding and this plugin version installed:

A ticket in `ready-for-architect` that an Architect passes through the gate reaches `in-progress` by the Architect's own transition, with the issue body's `board:meta` carrying `plan: <path>@<sha>` and `branch: <b>`, and no `ready-for-implementer` label ever appears on it. `sminos list` shows that Architect's seat `busy` throughout with a `NOW` column of the form `build: …`. The same seat later moves the ticket to `in-review` with a PR link. `ARCHITECT_MAX_CONCURRENT=1` holds a second architect dispatch back while that one builds (`execute-dispatch.sh --sweep` logs `architect cap reached (1)`).

`board-transition.sh <n> in-progress "plan-execution: p@<sha>" --plan pre-spec --branch b` from `in-design` exits non-zero and prints a message containing `down-shortcircuit`.

`agents/plan-executor.md` exists, and dispatching `doperpowers:plan-executor` from an interactive session against a small task-decomposed plan produces a PR without the session's own context filling with per-task dispatches.

All six test/lint commands in Milestone 5 pass, and the version in `.claude-plugin/plugin.json` is higher than before the change.


## Idempotence and Recovery


Every edit is a plain file change on a feature branch; re-running a milestone re-applies the same text (use the exact strings above to find already-applied edits before editing again). Test scripts create their own temporary state and clean it. The live check writes only under `/tmp/fold-live/` and one sminos seat, which `sminos retire fold-live --purge` removes; the seat's session transcript remains under `~/.claude/projects/-tmp-fold-live/` and is harmless. If the live check leaves a seat behind, `sminos list` shows it and the same retire command removes it. The version bump touches the files listed in `.version-bump.json`; re-running `scripts/bump-version.sh` with the same version is a no-op.


## Artifacts and Notes


Test summaries after Milestone 5 (worktree root, 2026-09-10):

    ### tests/issue-tracker/test-board-scripts.sh     exit=0   all tests passed
    ### tests/issue-tracker/test-execute-dispatch.sh  exit=0   all tests passed
    ### tests/issue-tracker/test-board-sweep.sh       exit=0   all tests passed
    ### tests/issue-tracker/test-protocol-content.sh  exit=0   all tests passed
    ### tests/sminos/run-sminos-tests.sh              exit=0   all 559 assertions passed
    ### scripts/lint-shell.sh                         exit=0   Linting 1 shell files

The new build-edge block inside test-board-scripts.sh:

    build edge:
      [PASS] a leaf Architect takes the build edge itself
      [PASS] the build edge records the plan pin
      [PASS] ...and the branch the sha is reachable from
      [PASS] --plan pre-spec is refused on the build edge
      [PASS] the refused build wrote nothing
      [PASS] the build edge without a pin is refused
      [PASS] the build edge is note-required
      [PASS] an epic is refused on the build edge
      [PASS] the refused epic build wrote nothing

Version: 7.81.0 → 7.82.0 via `scripts/bump-version.sh 7.82.0` (package.json,
.claude-plugin/plugin.json, .codex-plugin/plugin.json,
.claude-plugin/marketplace.json all in sync).

Live mechanism check (2026-09-10, seat `fold-live/fold-live`, `a48e663c`),
scratch repo `/tmp/fold-live`, plan `/tmp/fold-live/PLAN.md`, two milestones:

    ALIAS      GROUP      ROLE  STATUS   LIVE  SHORT     NOW
    fold-live  fold-live  -     working  busy  a48e663c
    fold-live  fold-live  -     working  busy  a48e663c  build: milestone 1/2
    fold-live  fold-live  -     working  busy  a48e663c  build: milestone 2/2
    fold-live  fold-live  -     working  idle  a48e663c  build: 2/2 done — commits on main; /tmp/fold-l…

    $ git -C /tmp/fold-live log --oneline
    1976a32 world
    0014b75 hello
    1657b46 plan: absolute sminos path
    cd7c73a plan
    5017d73 init

    $ sminos reply fold-live
    status: DONE_WITH_CONCERNS
    commit range: 1657b46..1976a32 — 0014b75 hello, 1976a32 world, both on main
    …

Seat retired with `sminos retire fold-live --purge`; `/tmp/fold-live` and its
worktree removed. The dispatch used the `general-purpose` / `opus` substitution
(see Surprises) because the installed plugin is still 7.81.0.

No PR: this branch is handed back to the session that authored the plan.


## Interfaces and Dependencies


`skills/issue-tracker/scripts/_board.py` must end with `"in-progress" in LEGAL["in-design"]` and `("in-design", "in-progress") in EDGE_NOTE_REQUIRED` and `("in-design", "in-progress") not in CONVERGENCE_EDGES`.

`skills/issue-tracker/scripts/board-transition.sh` must accept `--plan <path>@<sha40> --branch <b>` on `in-design → in-progress` for a leaf ticket, and refuse `--plan pre-spec` on that edge, a missing `--plan` on that edge, and the edge on an epic.

`skills/issue-tracker/scripts/execute-dispatch.sh`, function `_slots_used`, must count `("ready-for-architect", "in-design", "in-progress")` for the architect lane.

`agents/plan-executor.md` must exist with frontmatter `name: plan-executor`, `model: opus`, `effort: high`; it is addressed as `doperpowers:plan-executor`. The file itself is the body's contract (Milestone 2's text is the first draft, not the current one — see the Decision Log).

The Architect protocol's build transition string is exactly `board-transition.sh {{ISSUE_NUMBER}} in-progress "plan-execution: <repo-path>@<full-commit-sha>" --branch <branch> --plan <repo-path>@<full-commit-sha>`.

No new external dependency. The subagent nesting the design relies on (a subagent dispatching subagents and continuing them with SendMessage) and the harness's busy-while-a-subagent-runs reporting were both verified on 2026-09-10 and are recorded under Surprises & Discoveries.


## Revision Note — 2026-09-10 (fix wave, post-review)

An independent review of the branch returned four findings; all four are
implemented above and each has a Decision Log entry. Under one rule: **the
legacy handoff is the fallback whenever the build edge is refused for a stated
reason.** The build edge is the Architect's default exit, not its only one.

What changed against the plan as written:

1. `board-transition.sh`'s api path refuses `in-design → in-progress`
   client-side and names the handoff; the plan had assumed the edge was
   binding-agnostic, but legality there belongs to a board service whose state
   table does not carry it. Drilled in
   `tests/claude-code/board-api/test-register-transition.sh`, which also had a
   stale assertion on this branch (it still expected the pre-branch wording of
   the wrong-edge `--plan` refusal) — fixed with it.
2. The build edge now runs the surface-occupancy check. The plan's note that
   "`_surface_occupant` already treats `in-progress` as occupied; nothing to
   change" was true of the dispatcher and missed that the Architect enters
   `in-progress` without passing the dispatcher at all. The rule moved into
   `_board.surface_occupant`; `execute-dispatch.sh` calls it and its tests pass
   unmodified.
3. `skills/qa-loops/SKILL.md` (and the operation manual's summary of it) anchor
   the audit on whichever transition comment minted the pin, since the build
   edge mints one the audit did not know about.
4. `agents/plan-executor.md` carries the repo-facts contract, and the Architect
   and Executor protocols plus the issue-tracker state vocabulary name the
   handoff fallback.

Three further changes came from the human partner during the same wave and are
in the Decision Log: the plan-executor's progress line is gone (the Architect
sets its own seat status once before dispatching), its frontmatter description
is one sentence and its ExecPlan contract is inline, and `execplan`'s Step 3 is
back to `main` — interactive ExecPlan execution stays in the session.

Suites after the wave: `test-board-scripts.sh`, `test-execute-dispatch.sh`,
`test-board-sweep.sh`, `test-protocol-content.sh`, `run-sminos-tests.sh`,
`lint-shell.sh`, and `board-api/test-register-transition.sh` all green. No
version bump: 7.82.0 has not shipped — `main` is still 7.81.0.
