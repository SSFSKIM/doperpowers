# The Reviewer Fold Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-execution to implement this plan task-by-task. Deliverables use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The board's PR review loop becomes `doperpowers:qa-loop`, a subagent dispatched by the seat that owns the ticket; the qa-loops skill retires into that agent and the issue-tracker references; execution defaults to sol and the `engine:codex` route retires; the arkho board service lets the owner's run survive review.

**Architecture:** The Reviewer worker protocol is re-homed as an agent body with a five-line return contract; owner protocols dispatch it after the PR opens and answer three escalation kinds; a thin stand-in seat covers orphans and ticketless PRs; the review dispatcher shrinks to spawning stand-ins with an owner-first skip; the sweep's recover pass covers `in-review`; the board schema gains a re-pin self-edge, a convergence-counted rebuild edge, and a `review-trail` comment kind in both bindings.

**Tech Stack:** Bash board scripts with embedded Python (`_board.py`, `_board_api.py`), markdown protocols and agent bodies, hermetic shell test suites under `tests/`, the arkho board service (Node 22, Postgres, `node --test`).

**Spec:** `docs/doperpowers/specs/2026-09-21-reviewer-fold-design.md` (branch `reviewer-fold`). The plan argues from the spec; a conflict found during execution resolves against it and is returned to the dispatching session.

## Global Constraints

- Branch `reviewer-fold` in this repository; the arkho change on a branch of the same name off `origin/main` in `~/Developer/GitHub/arkho`, in its own worktree.
- No attribution lines in any commit message or PR body: no `Co-Authored-By`, no `Generated with`, no session URL.
- The version is bumped only with `scripts/bump-version.sh`, once, in the final records task, to the next version above `main`.
- Agent bodies and protocol files carry no `{{PLACEHOLDER}}`; the qa-loop agent body does not contain the string `Workflow(`.
- The qa-loop agent's frontmatter: `model: sol`, `effort: high`, `disallowedTools: Skill`. Its caps: 4 fix waves, 5 engine rounds, one closing wave outside the cap, a 45-minute hang bound.
- Exact strings (copy verbatim): return lines `DONE`, `PARKED <question>`, `NEEDS_PANEL level=<xhigh|max> base=<ref> baseCommit=<sha> headCommit=<sha> round=<n>`, `ESCALATE kind=<spec-conflict|design-gap|dismissal> finding=<id> …`, `ENGINE-UNAVAILABLE`; trail lines `[trail] dismissed <finding> — <pointer>: <reasoning>` and `[trail] re-pin <path>@<sha> — <delta>`; the dedupe skip line `#<pr>: owner reviews — skip`; the comment kind `review-trail`; the seat meta key `phase` with value `review`; gate comment `[gate] pass — <mode>: <one line>`.
- Bootstrap bindings added for the IMPLEMENT and ARCHITECT roles: `AUTO_MERGE` (`on`|`off`), `REVIEW_LEVEL` (one of `low|medium|high|xhigh|max`, default `medium`), `TECH_DEBT_ISSUE` (a number or `none`).
- Model pins after the flip: architect lane `${ARCHITECT_MODEL:-fable}`; implement and spike lanes `${IMPLEMENT_MODEL:-sol}`; stand-in `${REVIEW_MODEL:-sol}`; `agents/plan-executor.md` and `agents/task-executor.md` `model: sol`. No worker on fable or astra.
- Tests are hand-run shell suites; run each named suite from the repository root with `bash <path>`; `tests/claude-code/run-skill-tests.sh` runs the hermetic board-api suites and the bootstrap parity fence.
- "Your human partner" is the project's voice in protocol prose; keep it.

---

### Task 1: The qa-loop agent body

**Files:**
- Create: `agents/qa-loop.md`
- Create: `agents/codex/qa-loop.toml`
- Modify: `agents/codex/README.md` (model table)
- Modify: `tests/codex/test-native-agents.py:13-22` (MODELS)
- Create: `tests/issue-tracker/test-qa-loop-agent.sh`
- Read-only source: `skills/qa-loops/SKILL.md`, `skills/qa-loops/references/wave-board.md`, `skills/review-code/SKILL.md:34-51`, `skills/review-code/workflows/code-review.js:100-101`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the agent name `doperpowers:qa-loop`; the brief line set (below); the return contract (Global Constraints); the trail line formats; the tech-debt comment fields (finding, file:line, severity, why deferred).

**Deliverables:**
- [ ] `agents/qa-loop.md` exists with the frontmatter in Global Constraints and a body that is `skills/qa-loops/SKILL.md`'s Reviewer worker protocol re-homed per the Decisions below; `grep -c '{{' agents/qa-loop.md` prints 0 and `grep -c 'Workflow(' agents/qa-loop.md` prints 0. Commit: `agents: qa-loop — the board's review loop as a subagent of the ticket's owner`
- [ ] `agents/codex/qa-loop.toml` mirrors the body (name `doperpowers:qa-loop`, model `gpt-5.6-sol`, effort `high`, `developer_instructions` = the body with frontmatter stripped, no delegation tail — the agent dispatches fixers); `agents/codex/README.md`'s table gains the row; `tests/codex/test-native-agents.py` MODELS gains `"qa-loop": ("gpt-5.6-sol", "high")` and `python3 tests/codex/test-native-agents.py` passes. Commit: `agents/codex: qa-loop mirror`
- [ ] `tests/issue-tracker/test-qa-loop-agent.sh` asserts the body's structure (Tests below) and passes. Commit: `tests: structural fence over the qa-loop agent body`

**Tests:** `tests/issue-tracker/test-qa-loop-agent.sh` (modelled on `tests/qa-loops/test-skill-entrypoint.sh`'s `assert_contains` helpers; run `bash tests/issue-tracker/test-qa-loop-agent.sh`, expect `PASS` and exit 0) asserts:
- frontmatter lines `model: sol`, `effort: high`, and a `disallowedTools:` line containing `Skill` and not `Agent`;
- section headings in order: `## Role`, `## Orient`, `## Engine`, `## Compliance Audit`, `## Join`, `## Triage`, `## Fix Waves`, `## Re-review`, `## Escalate`, `## Scale review`, `## Authority`, `## Review Trail`;
- the four bins `WAVE`, `TOO BIG`, `LOG`, `INVALID`; the three kinds `spec-conflict`, `design-gap`, `dismissal`; the five return lines; `4 waves`, `5 engine rounds`, `closing wave`, `45 minutes`;
- the strings `P2 or P3`, `[trail] dismissed`, `[trail] re-pin`, `plausibly speaks`, `reads the pointed section`, `not in the tech-debt`, `which governs`, `one re-pin`, `second design-gap`, `isolation: "worktree"`, `doperpowers:reviewer-`, `Lens for this review:`, `review-trail`, `mktemp -d`, `hash`;
- absence of `{{`, `Workflow(`, `BIND_READY_FILE`, `MANIFEST_REF`, `SKILL_FILE`, `doperpowers:qa-loops`.

**Decisions:**
- Start from `skills/qa-loops/SKILL.md` lines 10–661 verbatim and apply deltas; do not paraphrase sections the spec lists as unchanged (compliance audit classes, JOIN, wave board grading, caps, merge gate, observation mode, scale verdicts, trail contents).
- Every `{{X}}` becomes prose "the brief names" or the concrete value: `{{BOARD_SCRIPTS}}` → "the board scripts directory the brief names (`<scripts>` below)"; `{{ISSUE_NUMBER}}`/`{{PR_NUMBER}}` → "the ticket"/"the PR"; `{{REVIEW_LEVEL}}` → "the floor the brief names"; `{{AUTO_MERGE}}` → "the auto-merge flag the brief names"; `{{TECH_DEBT_ISSUE}}`/`{{ENV_TRACKER_ISSUE}}` → the issue numbers the brief names; `{{IMPLEMENT_PROTOCOL_FILE}}` → the path the brief names; `{{REVIEW_MODE}}` → the mode the brief names; `{{WORKER_NAME}}` and the `mktemp -d` template → `mktemp -d "${TMPDIR:-/tmp}/qa-loop.XXXXXX"`.
- Role: "You review one pull request for the seat that owns its ticket and dispatched you. That seat authored or built the work and answers your escalations; it never grades your findings. Your escalation targets are the board, your human partner on their next wake, and — for exactly three kinds — your dispatcher." Delete the binding barrier paragraph and every reference to `BIND_READY_FILE`, the acknowledgement, the dispatcher control directory, and the `REVIEW_MODE api` bootstrap positioning (the stand-in positions the checkout).
- Brief lines the body expects, one per line, in this order: `mode: pr|scale`; `ticket: <n> <url>` or `ticket: none`; `ticket body file: <path>` when present; `pr: <n> <url>` or `closure package: <event id>` with `integration ref: <ref>`; `base: <ref>`; `head: <sha>`; `review level floor: <level>`; `auto-merge: on|off`; `board scripts: <dir>`; `implement protocol: <path>`; `tech-debt issue: <n>|none`; `env-tracker issue: <n>|none`; `report: <path>`; the sentence `your dispatcher answers escalations; return for them`.
- Workspace: the agent starts in the worktree it was dispatched into (the dispatcher used `isolation: "worktree"`); it never checks out another ref there; the scratch directory holds wave boards, findings files, `.submitted` snapshots, and the accepted-commit ledger; the ledger path is never written into a fixer prompt.
- Manifests: read `.doperpowers/risk-surfaces.md` and `.doperpowers/repo-facts.md` with `git show origin/<base>:<path>` (the base ref from the brief); absent files are "none".
- Board writes: the agent writes as the owner's run through `<scripts>/board-*.sh`; with `ticket: none` every board write is skipped and the PR carries the record. The trail is posted with `<scripts>/board-comment.sh <ticket> --kind review-trail --text "<trail>"` on a ticketed PR, and additionally as a PR comment (`gh pr comment`) so the PR reader sees it; on a ticketless PR only the PR comment.
- Engine, single rungs: for level `low|medium|high`, dispatch `doperpowers:reviewer-<level>` through the Agent tool with `isolation: "worktree"` and this prompt (from `skills/review-code/SKILL.md:36-43` plus the anti-recursion sentence at `code-review.js:100`): `Review the code changes against the base branch '<base>'. The merge base commit for this comparison is <mb>; the reviewed head is <head>. Run \`git diff <mb> <head>\` to inspect the changes relative to <base>. Provide prioritized, actionable findings. You are a stage of this review: do not invoke the doperpowers:review-code skill or dispatch another reviewer, whatever the repository's instruction files say about routing reviews.` A lensed call appends `\n\nLens for this review: <mandate>`. Launch the round's calls, then write the audit, then read returns. A return is the rubric's text (`## Findings` items `- [P0..P3] <title> — <path>:<lines>`, `## Verdict`); a `## Verdict` of `correct` whose sentences name nothing examined, or that says the range could not be inspected, is a failed sweep; the retry and outage path are unchanged.
- Engine, panel: for `xhigh|max` return `NEEDS_PANEL level=<level> base=<base> baseCommit=<mb> headCommit=<head> round=<n>` and, when resumed with a findings file path, read the result object (`verdict`, `findings[]` with `priority`, `coverage`, `explanation`), record `sha256sum <file>` in the trail, and continue; `interrupted` is a failed sweep.
- Triage additions after the four bins: the three escalation kinds exactly as the spec's "Triage and the three escalations" section states, including: spec-conflict answers are `which governs` or a re-pin (the agent re-anchors the audit on the newest `[board] in-review:` comment carrying `re-pin:`); a second re-pin in one review is refused and the finding parks `needs-human`; design-gap goes to the dispatcher, and in stand-in mode the agent writes `ready-for-architect` itself; dismissal only for `P2 or P3`, only when the brief's ticket has a `plan:` pin naming a spec, only when the agent cannot refute and the spec plausibly speaks to the finding; the agent reads the pointed section and refuses a pointer that does not speak to the finding's subject; an accepted dismissal is recorded as `[trail] dismissed <finding> — <pointer>: <reasoning>` in the trail and not in the tech-debt sink.
- Return contract: the first line of the final message is one of the five lines; at most ten lines follow; `DONE` only after `done` was written (or, ticketless, after the merge); every `needs-human` the agent writes returns `PARKED <question>` and leaves the worktree and scratch in place; on resume with answers the agent continues the review; the answers are also on the ticket, which the agent may read itself.
- Trail contents (in addition to today's list): the level and the auto-merge value used; the hash of any panel findings file; every `dismissed` line; every re-pin; the outage line and observation-mode line unchanged.
- Cleanup: a non-park terminal outcome removes the scratch directory after the trail is posted; the worktree is the dispatcher's to remove.
- The wave board reference is named by path as `<scripts>/../references/wave-board.md` (its new home after Task 6; until then the executor of this task writes the path as it will be — Task 6 moves the file).
- Codex mirror: `qa-loop` is not in `READ_ONLY` in the test; its `developer_instructions` is the body verbatim.

---

### Task 2: Board schema twins under the gh binding

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:46-56` (EDGE_NOTE_REQUIRED), `:150-152` (LEGAL in-review row)
- Modify: `skills/issue-tracker/scripts/board-transition.sh:196-229` (API build-edge refusal), `:372-397` (same-state path), `:483-549` (plan gates on the re-pin path)
- Modify: `skills/issue-tracker/scripts/board-comment.sh:45-48` (kinds)
- Modify: `skills/issue-tracker/SKILL.md` (state table row for `in-review`; the scripts table rows for `board-transition.sh` and `board-comment.sh`)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `board-transition.sh <n> in-review "<note>" --plan <path>@<sha>` as the re-pin (gh and API), which posts `[board] in-review: <note>`; `board-transition.sh <n> in-progress "<note>" --branch <b> --plan <pin>` accepted from `in-review` and convergence-counted; `board-comment.sh <n> --kind review-trail --text "<text>"`, rendered under gh as `[review-trail] <text>`; `board-transition.sh <n> in-progress … --plan` from `in-design` no longer refused under the API binding.

**Deliverables:**
- [ ] The rebuild edge is convergence-counted: `("in-review", "in-progress")` is in `EDGE_NOTE_REQUIRED` and not subtracted in `CONVERGENCE_EDGES`; a second worker traversal since the last human event transmutes to `needs-human` through the existing inline check. Commit: `board: the rebuild edge in-review → in-progress is convergence-counted`
- [ ] The re-pin: `in-review → in-review` with `--plan` is accepted on both bindings, requires a note, runs the plan-pin gates, writes the pin into `board:meta` (gh) or the `plan` request field (API), and posts `[board] in-review: <note>`; without `--plan`, or from any other state, a same-state transition is still refused with the existing message. Commit: `board: a same-state in-review transition with --plan re-pins the review contract`
- [ ] The API build-edge refusal at `board-transition.sh:225-226` and its comment are deleted; the two build-edge checks below it become reachable. Commit: `board: the API build edge is no longer refused client-side`
- [ ] `board-comment.sh` accepts `--kind review-trail`; gh renders `[review-trail] <text>`. Commit: `board: review-trail comment kind`
- [ ] `skills/issue-tracker/SKILL.md`'s state table `in-review` row names the re-pin self-edge and the counted rebuild edge; the scripts table rows name `--plan` on `in-review` and the `review-trail` kind. Same commit as the re-pin.

**Tests:** in `tests/issue-tracker/test-board-scripts.sh` (run `bash tests/issue-tracker/test-board-scripts.sh`, expect all cases PASS):
- `re-pin: in-review --plan writes the pin and posts [board] in-review:` — a ticket in `in-review` with a `pr:`; the transition with `--plan docs/x.md@<40-hex>` (the mock gh compare/contents fixtures the existing plan-gate cases use) leaves the state `in-review`, the meta `plan:` equal to the new pin, and a comment starting `[board] in-review: `.
- `re-pin refused without --plan` — same ticket, no `--plan`: exit non-zero, message contains `already in-review`.
- `re-pin refused from in-progress` — a same-state `in-progress` with `--plan`: refused.
- `rebuild edge counts toward convergence` — `in-review → in-progress` twice by a worker with no human comment between: the second lands in `needs-human` with a note starting `convergence:` (mirror the existing `in-review → ready-for-architect` convergence case).
- `review-trail kind renders its marker` — `board-comment.sh <n> --kind review-trail --text "level medium"` produces a comment body `[review-trail] level medium`.
- `test-board-scripts.sh` and `tests/claude-code/board-api/test-transition-*.sh` (if a build-edge refusal case exists there, invert it: the API build edge is sent to the server).

**Decisions:**
- Same-state handling in `board-transition.sh`: insert before the `if to == cur:` block at `:372` a branch `if to == cur == "in-review" and env["T_PLAN"]:` that skips the LEGAL lookup, requires a note (die with `a re-pin needs a note naming the delta`), and continues into the existing plan gates and `apply_state`; on the API path the same predicate skips nothing client-side beyond the plan gates — the server's legality row (Task 3) admits it.
- `apply_state`'s comment format needs no change: the self-edge is not in `CONVERGENCE_EDGES`, so it posts `[board] in-review: <note>`.
- The convergence count under gh is the inline block at `board-transition.sh:416-458`; adding the edge to `EDGE_NOTE_REQUIRED` is the whole mechanical change because `CONVERGENCE_EDGES` is derived by subtraction (`_board.py:65-67`). Do not add the edge to the subtraction set.
- `PRE_PARK["in-review"]` is already `in-review`; no change.
- Keep `board-comment.sh`'s closed-set die message in sync with the new kind list.

---

### Task 3: The arkho board service

**Files** (all under `~/Developer/GitHub/arkho/board-service`, in a new worktree `~/Developer/GitHub/arkho/.worktrees/reviewer-fold` on branch `reviewer-fold` from `origin/main`):
- Modify: `src/states.js:38-41` (ESCALATION_EDGES unchanged), `:64-136` (LEGAL_ROWS)
- Modify: `src/transitions.js:24-32` (SCOPE_END, LANE_CROSS), `:119-164` (terminal authority), `:169-184` (convergence), `:202-206` (park insert), `:213-223` (phase end), and the `pr` write site for `in-review` entries
- Modify: `src/answers.js:140-151` (RESUME arm), `:88-91` (park read)
- Modify: `src/tickets.js:250-251` (COMMENT_KINDS)
- Modify: `schema.sql` after `:124` (decision_park) — `alter table board.decision_park add column if not exists from_state text;`
- Modify: `src/server.js:582-584` (route comment)
- Modify: `API.md:223-232`, `:286-297`, `:700-714`, `:716-724`, `:749`, `:1304-1327`, `:1766-1788`, `:2047-2067`
- Test: `test/transitions.test.js`, `test/answers.test.js`, `test/claims.test.js`, `test/api-doc.test.js` (doc parity)

**Interfaces:**
- Consumes: the kind name `review-trail` and the edge set from Task 2 (names only).
- Produces: a deployed service where an architect run may write `in-design → in-progress`, an owner run survives `in-progress → in-review` and `in-review → in-progress`, may re-pin `in-review → in-review`, closes `in-review → done` when it owns the ticket, the package matches, and a `review-trail` event by it exists after the latest `in-review` entry; a bound park returns to the state it interrupted.

**Deliverables:**
- [ ] Worktree and test database: `git -C ~/Developer/GitHub/arkho fetch origin && git -C ~/Developer/GitHub/arkho worktree add .worktrees/reviewer-fold -b reviewer-fold origin/main`; `TEST_DATABASE_URL` located (shell env, `board-service/.env*`, arkho docs) or a local Postgres started (`pg_isready`, else `docker run -d -e POSTGRES_PASSWORD=x -p 5433:5432 postgres:16` and `TEST_DATABASE_URL=postgres://postgres:x@127.0.0.1:5433/postgres`); `npm test` green on `origin/main` before any edit. No commit; a missing database is a `BLOCKED` return naming it.
- [ ] Legal rows: `['in-design','in-progress',false,false]` and `['in-review','in-review',true,false]` added to `LEGAL_ROWS`; API.md Appendix A gains both rows; `api-doc.test.js` parity passes. Commit: `states: the architect build edge and the in-review re-pin self-edge`
- [ ] `LANE_CROSS` no longer contains `in-progress→in-review` or `in-review→in-progress`; convergence counts a new module-level `COUNTED = new Set([...esc, 'in-review→in-progress'])` instead of `esc` (LANE_CROSS keeps `...esc`); the existing release drills 3 and 3b are rewritten to assert the run SURVIVES `in-progress → in-review` and a qagent claim then finds nothing (owned), and a new drill asserts `in-review → in-progress` by a worker twice transmutes the second to `needs-human`. Commit: `transitions: the owner's run survives review and its rebuild; the rebuild edge is convergence-counted`
- [ ] Terminal authority: the `in-review → done` arm becomes ownership + package + trail as in Code below; `review-required` unchanged in code, its comment updated; a run's write into `in-review` whose `pr` parses as a number stamps `run.package_event_id`. Tests: a leaf closed by its owning implementer run after a `review-trail` event; the same refused with `review-trail-required` when no trail exists after the latest `in-review` entry (including a trail posted before a re-pin); an epic closed by its owning architect run whose stamped package equals `pr_url`; refused with `epic-guard` when they differ; the existing qagent stand-in cases still pass. Commit: `transitions: in-review → done closes for the owning run with package match and a review-trail artifact`
- [ ] `decision_park.from_state` written at park time from the transition's `from`; `answers.js` RESUME arm returns to `from_state` when `IN_FLIGHT.includes(from_state)`, else `LANE_INFLIGHT[run.lane]`; test: an architect run parked from `in-review` resumes into `in-review`, from `in-progress` into `in-progress`, and a legacy row with null `from_state` into `in-design`. Commit: `answers: a bound park resumes into the state it interrupted`
- [ ] `COMMENT_KINDS` gains `review-trail`; route comment and API.md kinds list updated; test: `addComment` with `kind:'review-trail'` appends the event and a `bad-kind` for an unknown kind still 400s. Commit: `tickets: review-trail comment kind`
- [ ] API.md: lane table note that an owning run may hold a ticket through `in-review`; the pick-order sentence "Fix waves land here …" replaced by "an owned `in-review` ticket is not a candidate; a reclaimed one is"; terminal authority bullets rewritten for the ownership rule and the `review-trail-required` code; the Convergence section lists `in-review → in-progress`; the park-answer route's bound mode says it returns to the interrupted state; the Transitions error table gains `review-trail-required` (403). Same commits as the code they document.
- [ ] `npm test` green; the branch pushed; a pull request opened on arkho titled `board-service: the owner's run survives review (reviewer fold)` whose body lists the seven changes and says the deploy follows the merge. The merge is not this task's. Report the PR URL.

**Tests:** `cd ~/Developer/GitHub/arkho/.worktrees/reviewer-fold/board-service && TEST_DATABASE_URL=… npm test`, expect all files pass; the new cases sit beside `transitions.test.js:176`, `:208`, `:693`, `:794`, `:928`, `:976` and `answers.test.js:153`.

**Decisions:**
- Do not touch the `agent-grade-reads` checkout; work only in the new worktree.
- The `pr` write on `in-review` entry: find where `transition()` writes `tk.pr_url` from the request's `pr` (the `fieldChange` helper); after it, when `actor.cls === 'run'` and `Number(pr)` is a finite integer, `update board.run set package_event_id=$1 where id=$2`.
- The trail predicate: `select 1 from board.ticket_event where ticket_id=$1 and kind='review-trail' and run_id=$2 and id > coalesce((select max(id) from board.ticket_event where ticket_id=$1 and kind='transition' and to_state='in-review'),0) limit 1`.
- Error code for a missing artifact: `review-trail-required`, status 403, message `in-review → done needs a review-trail event by this run after the latest entry into in-review`.
- A same-state `in-review → in-review` request: check `transition()` for an early `from === to` refusal; if one exists, exempt exactly this pair; the write must not fire phase-end (it is in neither LANE_CROSS nor SCOPE_END) nor the epic pull.
- The `from_state` column: `alter table board.decision_park add column if not exists from_state text;` placed after the table's indexes, with a comment citing the `:94-100` idempotence precedent.
- Render deploys `main` automatically (no `autoDeploy`/`branch` keys in `render.yaml`); do not add them.

**Code:**

```js
// transitions.js — the in-review → done arm, replacing :143-156
} else if (from === 'in-review' && to === 'done') {
  const owns = run.id === tk.owner_run;
  const pkgOk = isEpic
    ? run.package_event_id != null && String(run.package_event_id) === String(tk.pr_url)
    : tk.pr_url != null && Number.isNaN(Number(tk.pr_url));
  if (!(owns && pkgOk)) throw new BoardError('epic-guard', 403,
    'in-review → done is the owning run\'s close — an epic needs the package this run reviewed; a leaf needs its PR URL');
  if (!(await hasReviewTrail(c, ticketId, run.id))) throw new BoardError('review-trail-required', 403,
    'in-review → done needs a review-trail event by this run after the latest entry into in-review');
}
```

---

### Task 4: The model flip and the route retirement

**Files:**
- Modify: `agents/plan-executor.md:4`, `agents/task-executor.md:4`
- Modify: `skills/issue-tracker/scripts/execute-dispatch.sh:28-49` (header), `:359-367`, `:378-386`, `:551-576`, `:818-830`, `:923-955`, `:1018`
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh:94`, `:1564-1569`, `:2340`
- Modify: `skills/qa-loops/scripts/review-dispatch.sh:28-46`, `:288`, `:457`, `:505`, `:626-639`, `:715`, `:745-752`, `:866`, `:965-1017`, `:1231`, `:1656-1659`, `:1743`, `:2022-2029`
- Modify: `skills/issue-tracker/references/worker-bootstrap.md:31`, `implement-worker-protocol.md:99`, `spike-worker-protocol.md:47`, `architect-worker-protocol.md:251-252`, `execution-loop.md:131-133`, `sweep-setup.md:100-110`
- Modify: `skills/issue-tracker/SKILL.md:49`, `:91`, `:310-355`
- Modify: `skills/qa-loops/references/operation-manual.md:30`, `:243-247`
- Modify: `skills/subagent-driven-execution/SKILL.md:112-125`, `:142`
- Modify: `CLAUDE.md:80`
- Modify: `infra/worker-host/README.md:160-167`, `infra/worker-host/env.example:24-28`
- Test: `tests/issue-tracker/test-execute-dispatch.sh`, `tests/issue-tracker/test-protocol-content.sh`, `tests/qa-loops/test-review-dispatch.sh`, `tests/claude-code/board-api/test-review-dispatch-claim.sh:240-244`

**Interfaces:**
- Consumes: nothing.
- Produces: `IMPLEMENT_MODEL` default `sol`; `REVIEW_MODEL` default `sol`; no `ENGINE_NAME` binding; gate comment format `[gate] pass — <mode>: <one line>`.

**Deliverables:**
- [ ] The two agent pins read `model: sol`; `test-protocol-content.sh:459-463` asserts `model: sol`. Commit: `agents: plan-executor and task-executor on sol`
- [ ] `execute-dispatch.sh`: the engine-label selector, `T_ENGINE_LABEL`, `WORKER_ENGINE`, the codex branch, `CLODEX_*`, `P_ENGINE_NAME`, and the `engine=` echo are deleted; implement and spike pin `${IMPLEMENT_MODEL:-sol}`, architect `${ARCHITECT_MODEL:-fable}`; `_sweep_api.sh` `_model_for_lane` returns `${IMPLEMENT_MODEL:-sol}` for non-architect lanes. Commit: `dispatch: one route — sol for execution, fable for design; the engine label retires`
- [ ] `review-dispatch.sh`: the same deletions; every spawn pins `${REVIEW_MODEL:-sol}` with `DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT="${REVIEW_EFFORT:-high}"`; the legacy codex-CLI liveness arms (`:457`, `:505`) stay (they guard old registry records). Commit: `review-dispatch: one route, sol`
- [ ] `ENGINE_NAME` leaves `worker-bootstrap.md`; the two gate comment templates read `[gate] pass — <mode>: <one line>` / `[gate] pass — spike: <one line>`; `test-protocol-content.sh:81,107,127,245` no longer require or exempt it. Commit: `bootstrap: the engine name binding retires`
- [ ] Prose: `sweep-setup.md` knobs `IMPLEMENT_MODEL | sol`, `REVIEW_MODEL | sol`, `WORKER_ENGINE` row removed; issue-tracker `SKILL.md` step 2's engine paragraph replaced by one sentence ("every worker is a Claude-harness seat; `--model` names its model and the gateway serves it"), step 3's spawn lines updated, the role table's "Fable route" wording kept; `execution-loop.md`'s engine-label bullet removed; the architect protocol's exemption sentence removed; the operation manual's route sentence and adoption checklist items on `WORKER_ENGINE`/`clodex` removed; `infra/worker-host` docs drop `WORKER_ENGINE`. Commit: `docs: the model route is one gateway and a model name`
- [ ] `subagent-driven-execution/SKILL.md` Model selection: `task-executor` pinned to sol at high, the task grain calibrated to that tier; `task-reviewer` on sol at high; `model: sonnet` the cheap override; "Never dispatch workers on fable or astra"; BLOCKED ladder `sonnet → sol; from sol there is no tier above — the difficulty moves into the brief`; line 142 to match. `CLAUDE.md:80` agents row: `plan-executor (sol/high)`, `task-executor (sol/high)`. Commit: `sde: the executor tier is sol`
- [ ] Tests re-anchored and green: `test-execute-dispatch.sh` (`[model=sol]` on implement, `model=fable` on architect; the engine-label and `WORKER_ENGINE` cases deleted; the sweep case no longer counts gateway spawns), `test-review-dispatch.sh` (`--model sol`; the engine-switch section `:1688-1776` and the scale engine-label section `:2168-2210` deleted; the `export WORKER_ENGINE` at `:362` removed), `test-review-dispatch-claim.sh` (`model=sol`), `test-protocol-content.sh`. Commit with the suite each belongs to.

**Tests:** `bash tests/issue-tracker/test-execute-dispatch.sh`, `bash tests/issue-tracker/test-protocol-content.sh`, `bash tests/qa-loops/test-review-dispatch.sh`, `bash tests/claude-code/board-api/test-review-dispatch-claim.sh`, `python3 tests/codex/test-native-agents.py`, `scripts/lint-shell.sh` — all green.

**Decisions:**
- `sminos.py` is untouched: `--settings`/`--effort`, `gateway_env_keys()`, and `launch_env()` are general mechanisms; `tests/sminos/run-sminos-tests.sh`'s gateway dimension stays as is.
- `agents/codex/*.toml` already say `gpt-5.6-sol`; only `tests/codex/test-native-agents.py` is unaffected by the pin change (it reads the toml, not the frontmatter model).
- Keep `REVIEW_EFFORT` (default `high`) as the stand-in's effort knob; delete `CLODEX_EFFORT`.
- The `engine:claude` label on this repository's GitHub is not deleted by this task (labels are board data); `board-lint.sh` need not know it.

---

### Task 5: Owner bootstrap bindings and lane caps by phase

**Files:**
- Modify: `skills/issue-tracker/scripts/execute-dispatch.sh:186-213` (`_api_registry_count`), `:249-262` (new validation, modelled on `review-dispatch.sh:249-262`), `:383-390` and `:923-931` (render sites), `:696-756` (`_slots_used`, unchanged logic — verify it already excludes `in-review`)
- Modify: `skills/issue-tracker/scripts/board-transition.sh` (stamp `phase` on the bound seat's meta)
- Modify: `skills/issue-tracker/references/worker-bootstrap.md:25-34`
- Modify: `skills/issue-tracker/references/sweep-setup.md` knobs (`AUTO_MERGE_ENABLED`, `REVIEW_LEVEL` rows)
- Test: `tests/issue-tracker/test-execute-dispatch.sh`, `tests/claude-code/board-api/test-dispatch-claim.sh`, `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: bootstrap lines `- \`AUTO_MERGE\`: {{AUTO_MERGE}}`, `- \`REVIEW_LEVEL\`: {{REVIEW_LEVEL}}`, `- \`TECH_DEBT_ISSUE\`: {{TECH_DEBT_ISSUE}}` rendered for IMPLEMENT and ARCHITECT; seat meta key `phase` = `review` while the seat's ticket is in `in-review`, absent otherwise.

**Deliverables:**
- [ ] `worker-bootstrap.md` carries the three bindings with one-line meanings; both render sites pass `P_AUTO_MERGE` (from `AUTO_MERGE_ENABLED`, `on`/`off`, default `off`), `P_REVIEW_LEVEL` (from `REVIEW_LEVEL`, validated against `low|medium|high|xhigh|max`, default `medium`, refused before any spawn with `REVIEW_LEVEL must be one of …`), `P_TECH_DEBT_ISSUE` (gh: `gh issue list --label tech-debt --state open --limit 1 --json number -q '.[0].number'` or `none`; API: `none`). Commit: `dispatch: the owner carries the review floor, the auto-merge switch, and the tech-debt sink`
- [ ] `board-transition.sh` stamps the ticket's bound seat meta `phase=review` on any transition into `in-review` and removes the key on any transition out of it, on both bindings, using the existing `_meta_put`-style locked write (the seat is resolved the way the live-owner fence resolves it at `:134-184`); a transition with no bound seat stamps nothing. Commit: `board: a seat in review is marked in its meta`
- [ ] `_api_registry_count` excludes metas whose `phase` is `review`; `_slots_used` is verified to exclude `in-review` by its state tuples (no change expected; add a comment naming the parity). Commit: `dispatch: an owner in review holds no lane slot`
- [ ] `sweep-setup.md` knobs table gains `AUTO_MERGE_ENABLED | off` and `REVIEW_LEVEL | medium` rows for the execute dispatcher.

**Tests:**
- `test-execute-dispatch.sh`: `rendered prompt carries AUTO_MERGE, REVIEW_LEVEL, TECH_DEBT_ISSUE` (a gh dispatch with `AUTO_MERGE_ENABLED=true REVIEW_LEVEL=high` and a mock tech-debt issue 90 renders `AUTO_MERGE`: `on`, `REVIEW_LEVEL`: `high`, `TECH_DEBT_ISSUE`: `90`); `invalid REVIEW_LEVEL refuses to dispatch` (`REVIEW_LEVEL=loud` → exit non-zero before any spawn, no spawn logged).
- `test-dispatch-claim.sh`: `an architect seat in review does not hold the architect slot` (one meta `lane:architect, status:idle, run_id:…, phase:review`, `ARCHITECT_MAX_CONCURRENT=1` → the claim proceeds); `an architect seat in design holds it` (same meta without `phase` → no claim).
- `test-board-scripts.sh`: `entering in-review stamps phase=review on the bound seat; leaving clears it`.

**Decisions:**
- `AUTO_MERGE_ENABLED` and `REVIEW_LEVEL` are read from the dispatcher's environment exactly as `review-dispatch.sh:249-262` does today; copy that validation shape.
- The `phase` key is written with the same lock discipline as `sweep_recoveries` (`board-sweep.sh:204`) — a small helper in `_lib.sh` if none exists; never rewrite `updated`.

---

### Task 6: Move the review loop's files into issue-tracker

**Files:**
- Move: `skills/qa-loops/scripts/review-dispatch.sh` → `skills/issue-tracker/scripts/review-dispatch.sh`
- Move: `skills/qa-loops/references/wave-board.md` → `skills/issue-tracker/references/wave-board.md`
- Move: `skills/qa-loops/references/operation-manual.md` → `skills/issue-tracker/references/review-loop.md`
- Move: `skills/qa-loops/references/review-worker-bootstrap.md` → `skills/issue-tracker/references/review-standin-bootstrap.md`
- Move: `skills/qa-loops/references/pr-review-dispatch.yml`, `runner-setup.md` → `skills/issue-tracker/references/`
- Move: `tests/qa-loops/test-review-dispatch.sh`, `test-bootstrap-parity.sh`, `test-skill-entrypoint.sh` → `tests/issue-tracker/` (the last renamed `test-review-standin.sh`)
- Delete: `skills/qa-loops/SKILL.md` and the directory
- Modify: `skills/issue-tracker/scripts/board-sweep.sh:129` (`REVIEW_DISPATCH_CMD`), `_sweep_api.sh:2735` (`revw`), `tests/claude-code/run-skill-tests.sh:135`, `skills/issue-tracker/references/pr-review-dispatch.yml:48`, `README.md:84`, `CLAUDE.md:81` (skills row: 16 skills, the review loop's references), every `SKILL_DIR`/`${SKILL_DIR%/*}` derivation inside the moved dispatcher (`:151`, `:265`, `BOOTSTRAP_TEMPLATE`), every path inside the moved tests that names `skills/qa-loops` or `tests/qa-loops`

**Interfaces:**
- Consumes: nothing.
- Produces: the new paths; `pr-review-dispatch.yml` invoking `skills/issue-tracker/scripts/review-dispatch.sh`.

**Deliverables:**
- [ ] `git mv` for every move; `skills/qa-loops` gone; `ls skills | wc -l` prints 16; every moved file's internal paths resolve (`bash -n` on scripts; the dispatcher's `IMPLEMENT_PROTOCOL_FILE` and `REVIEW_CODE_DIR` derivations now read `$SKILL_DIR/references/implement-worker-protocol.md` and `${SKILL_DIR%/*}/review-code`). Commit: `issue-tracker: the review loop's files move in; the qa-loops skill retires`
- [ ] The three moved suites pass at their new paths (`test-review-standin.sh` with only its bootstrap and wiring assertions); `run-skill-tests.sh` lists `../issue-tracker/test-bootstrap-parity.sh`; a structural assertion in `test-review-standin.sh` checks `pr-review-dispatch.yml` runs `skills/issue-tracker/scripts/review-dispatch.sh`. Commit: `tests: the review loop's suites move to issue-tracker`
- [ ] `grep -rn 'doperpowers:qa-loops\|skills/qa-loops\|tests/qa-loops' skills agents hooks scripts tests CLAUDE.md README.md` returns nothing except revision-note prose in `docs/`. Same commit.

**Tests:** `bash tests/issue-tracker/test-review-dispatch.sh`, `bash tests/issue-tracker/test-bootstrap-parity.sh`, `bash tests/issue-tracker/test-review-standin.sh`, `bash tests/claude-code/run-skill-tests.sh` — green.

**Decisions:**
- Pure relocation: no behavior change in this task beyond path derivations; the shrink is Task 7. `test-skill-entrypoint.sh`'s assertions over `skills/qa-loops/SKILL.md`'s body are deleted in this task (the file they read is gone; Task 1's fence covers the agent body); its bootstrap-placeholder and dispatch-wiring assertions stay with their paths updated, and Task 7 rewrites them for the stand-in.
- `README.md:84`'s codex-companion blurb drops "the qa-loops review engine still runs its runtime".

---

### Task 7: The stand-in seat and the shrunk dispatcher

**Files:**
- Modify: `skills/issue-tracker/scripts/review-dispatch.sh` (moved): dedupe (`run_for` and the sweep loop), `_spawn_reviewer` (`:965-1108` old numbering), the three render sites, the manifest snapshots (`:661-664`, `:828-831`, `:1670-1679`), the control-directory and barrier code (`:690-701`, `:838-851`, `:1058-1101`, `:1681-1696`), the API `qagent` claim handover (`:1734-1817`)
- Rewrite: `skills/issue-tracker/references/review-standin-bootstrap.md`
- Create: `skills/issue-tracker/references/review-standin-protocol.md`
- Modify: `skills/issue-tracker/references/review-loop.md` (pieces table, dedupe policy table, failure cap, a migration note for installed `pr-review-dispatch.yml` copies, the removed knobs)
- Modify: `skills/issue-tracker/references/wave-board.md:48-54` (the barrier sentences → the agent's scratch directory), `:62` (fixer dispatch: "the Agent tool, general-purpose")
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh:2291-2297` (the QAGENT refusal message: a stand-in is fresh-spawnable by the review dispatcher's claim; wording only)
- Modify: `skills/issue-tracker/SKILL.md:49-52` (roles table: the QA agent row; Reviewer Worker row → stand-in)
- Test: `tests/issue-tracker/test-review-dispatch.sh`, `test-bootstrap-parity.sh`, `test-review-standin.sh`

**Interfaces:**
- Consumes: from Task 1 the agent name, brief lines, and return contract; from Task 4 `${REVIEW_MODEL:-sol}`; from Task 5 the `phase` key (not used here).
- Produces: the stand-in bootstrap roster (spec acceptance 5) and `review-standin-protocol.md`; the dedupe line `#<pr>: owner reviews — skip`.

**Deliverables:**
- [ ] Owner-first dedupe: in triggered and sweep modes, after resolving the PR's primary ticket and before any registry dedupe, read the seat registry for a meta bound to that ticket whose `role` is not `QAGENT` and whose status is `working|blocked|idle`; if found, print `#<pr>: owner reviews — skip` and return; a `QAGENT`-bound ticket falls through to the existing dedupe. Commit: `review-dispatch: a ticket with a live owner is the owner's review`
- [ ] The bootstrap: exactly the roster in spec acceptance 5, four mode blocks kept (`pr`, `scale`, `api`, `api-scale`) but each reduced to positioning facts; no `SKILL_FILE`, `BIND_READY_FILE`, `MANIFEST_REF`, `RISK_MANIFEST`, `REPO_FACTS`; the tail says `Your protocol is the dispatcher-pinned copy at {{PROTOCOL_FILE}}` — add `PROTOCOL_FILE` to the roster, bound to `$SKILL_DIR/references/review-standin-protocol.md`. Commit: `review-dispatch: the stand-in bootstrap`
- [ ] `review-standin-protocol.md`: Role (a stand-in owner for a review nobody live owns; makes no judgment); Position (PR: fetch base and head, `git checkout --detach <HEAD_SHA>`; scale: fetch and check out the integration ref, resolve the base from `origin`'s HEAD symref; api: resolve base/head from `gh pr view --json baseRefName,headRefName,headRefOid` as today's `mode:api` block says); Dispatch (one `doperpowers:qa-loop` with `isolation: "worktree"` and the brief lines, `ticket body file` when `TICKET_BODY_FILE` is bound); Relay (`NEEDS_PANEL`: fast-forward or detach the checkout at the requested `headCommit`, run the `Workflow(...)` call from `skills/review-code/SKILL.md:45-51` in the background, save the result to a file, resume the agent; `PARKED`: end the turn, forward answers on resume; `ESCALATE`: design-gap → `board-transition.sh <n> ready-for-architect "<impasse>"` and end, spec-conflict → `ready-for-architect` on a pinned plan or `needs-human` on a body, dismissal → refuse: reply `no dismissal channel from a stand-in` so the finding waves; `ENGINE-UNAVAILABLE`: post nothing further, end the turn with that as the last line; `DONE`: remove the agent's worktree, end). Commit: `issue-tracker: the review stand-in protocol`
- [ ] `_spawn_reviewer` keeps: name, `--role QAGENT`, `--stamp`, the registry bind and retries, the `QAGENT` role stamp, `_finalize_ticket_owners`; deletes: the control directory, the accepted-commit ledger file, the bind-ready publish and ack poll, `SKILL_FILE`; the manifest snapshot reads and their `P_*` are deleted at all three render sites; `REVIEW_ACK_*` knobs removed. Commit: `review-dispatch: no barrier, no ledger, no manifest snapshot — the agent reads the base ref itself`
- [ ] `wave-board.md`: the "binding barrier supplies the ledger" sentences replaced by "the accepted-commit ledger lives in the agent's scratch directory, outside the worktree, and its path is never written into a fixer prompt"; the fixer dispatch line reads "the Agent tool, `general-purpose`". `review-loop.md`: pieces table rows for the agent, the stand-in protocol, the stand-in bootstrap, the dispatcher; the dedupe table gains the owner row first; a `## Migrating an installed workflow` note: replace the command path in the repository's copy of `pr-review-dispatch.yml`. `SKILL.md` roles table: `QA agent (subagent of the owning seat, sol)` row with its authority (the PR's ticket open states as the owner's run, finding tickets, the merge, `done` post-merge) and `Review stand-in (seat, one PR nobody owns)`. Commit: `docs: the review loop's references describe the fold`

**Tests:** in `tests/issue-tracker/test-review-dispatch.sh` (run `bash tests/issue-tracker/test-review-dispatch.sh`):
- `owner-first: a ticket bound to a live architect seat is skipped` — seed `in-review` ticket 12 with PR 5, a meta `{"name":"12-arch-slug","ticket":"12","role":"ARCHITECT","status":"idle",...}`; triggered dispatch of PR 5 prints `#5: owner reviews — skip` and spawns nothing.
- `owner-first: an implement seat too` — role `IMPLEMENT`, same outcome.
- `no live owner: the stand-in spawns` — no meta → a spawn with `--role QAGENT`, the rendered prompt carrying `PROTOCOL_FILE` ending `review-standin-protocol.md` and none of `BIND_READY_FILE`, `MANIFEST_REF`, `SKILL_FILE`.
- `a finished stand-in with ENGINE-UNAVAILABLE reaches the streak decision` — a `QAGENT` meta with a reply file ending `ENGINE-UNAVAILABLE`: the existing outage-cap case's expectations hold (this is the existing case re-anchored, not a new one).
- `test-bootstrap-parity.sh`: the review side's placeholder set is the roster in spec acceptance 5 plus `PROTOCOL_FILE`.
- `test-review-standin.sh`: the protocol file carries `Position`, `Dispatch`, `Relay`, the five return lines, `no dismissal channel`, and `ENGINE-UNAVAILABLE` as the echo; the bootstrap has no `SKILL_FILE`; the Action's command path.
- The existing barrier/ack/ledger cases in `test-review-dispatch.sh` are deleted with the mechanism; the stale-reviewer, cap, dedupe, worktree-guard, scale, and API claim cases stay green.

**Decisions:**
- The registry read for owner-first reuses `_reviewer_meta`'s JSON parsing; "live" is `status in working|blocked|idle` and the same host and boot the existing `_decide` uses; a stalled owner is still live here — the sweep's recover pass (Task 9) handles stalls.
- The API `qagent` claim path is unchanged in shape: the claim delivers the body file; the stand-in binds `TICKET_BODY_FILE` and the brief carries it.
- `WORKER_NAME` stays in the roster (the registry identity the stand-in uses for `sminos status`).

---

### Task 8: The owner protocols

**Files:**
- Modify: `skills/issue-tracker/references/architect-worker-protocol.md` (Build's "While it runs" paragraph, Closing Artifact, If Resumed With Answers, Authority)
- Modify: `skills/issue-tracker/references/implement-worker-protocol.md` (Closing Artifact, If Resumed With Answers, Authority)
- Modify: `agents/plan-executor.md` (Finishing: "a review loop owns them (the board's does, from the PR on)" → "the owning seat's QA agent owns them on the board")
- Modify: `skills/issue-tracker/references/execution-loop.md` (Execution section: the review loop is the owner's QA agent; the no-live-progress paragraph)
- Test: `tests/issue-tracker/test-protocol-content.sh`

**Interfaces:**
- Consumes: from Task 1 the agent name, brief lines, return contract, trail formats; from Task 2 the re-pin command and the rebuild edge; from Task 5 the bindings `AUTO_MERGE`, `REVIEW_LEVEL`, `TECH_DEBT_ISSUE`.
- Produces: nothing downstream.

**Deliverables:**
- [ ] Architect Closing Artifact rewritten per the spec's "The owner's side": after `in-review --pr --branch`, set the seat status line (`sminos status <alias> "reviewing: <PR URL>"`), dispatch ONE `doperpowers:qa-loop` with `isolation: "worktree"` and the brief lines (values from the bootstrap bindings and `gh pr view`; `ticket body file` when the bootstrap named one), and end the turn; then the five returns with their responses, verbatim rules: `NEEDS_PANEL` — `git fetch origin <branch> && git merge --ff-only origin/<branch>` then `[ "$(git rev-parse HEAD)" = <headCommit> ]`, the `Workflow({ scriptPath: "<BOARD_SCRIPTS>/../../review-code/workflows/code-review.js", args: { level, base, baseCommit, headCommit } })` call in the background, save the result object to `<report dir>/findings-r<N>.json` without acting on its contents, resume the agent with the path; `ESCALATE kind=spec-conflict` — reply `which governs: <text>` or re-pin (`git commit` the repaired document, then `board-transition.sh <n> in-review "re-pin: <delta>" --plan <path>@<sha>`, then reply `re-pin: <path>@<sha>`); a second re-pin request in one review is answered `park` and the agent parks it; `ESCALATE kind=design-gap` — one of repair-and-rebuild (`git fetch origin <branch> && git merge --ff-only origin/<branch>`, repair the plan, commit, push, `board-transition.sh <n> in-progress "rebuild: <why>" --branch <b> --plan <path>@<sha>`, dispatch plan-executor per Build, and on its `DONE` re-enter this section), a corrective follow-up (`board-register.sh … --spawned-by <n>`, reply `follow-up #<m>`), or `park`; a second design-gap on the same ticket is `park` with both positions; `ESCALATE kind=dismissal` — reply `dismiss: <section heading or Decision Log entry> — <reasoning>` only for a P2/P3 the pinned spec speaks to, else `wave`; `PARKED` — end the turn keeping the worktree; when `board-answer` resumes you, forward the answers verbatim to the agent with `SendMessage`; `ENGINE-UNAVAILABLE` — end the turn with the ticket in `in-review`; on the sweep's `resume the review` nudge, dispatch a fresh agent; `DONE` — `git worktree remove` the agent's worktree, end. Authority: "never grade, triage, or merge your own pull request's review — the QA agent does; you answer its escalations"; the terminal-state prohibition gains "(`done` is written by your QA agent after the merge)". Commit: `architect protocol: the review runs as the Architect's QA agent`
- [ ] Implement Closing Artifact: the same dispatch after opening the PR ready for review; `ESCALATE kind=design-gap` and `kind=spec-conflict` on a pinned plan → `board-transition.sh <n> ready-for-architect "<impasse>" --branch <b>` and end (convergence-counted); `spec-conflict` on a body-only ticket → `needs-human` with both positions; `dismissal` → reply `wave`; the rest as the Architect's. Authority: the same sentence. Commit: `implement protocol: the review runs as the Executor's QA agent`
- [ ] `plan-executor.md` and `execution-loop.md` wording per Files. Same commit as the architect protocol.

**Tests:** `tests/issue-tracker/test-protocol-content.sh` (run `bash tests/issue-tracker/test-protocol-content.sh`) asserts in the architect protocol: `doperpowers:qa-loop`, `isolation: "worktree"`, the five return lines, `merge --ff-only`, `findings-r`, `re-pin: `, `--plan`, `rebuild: `, `second design-gap`, `dismiss: `, `never grade, triage, or merge`; in the implement protocol: `doperpowers:qa-loop`, `ready-for-architect`, `reply \`wave\``, the same authority sentence; in `plan-executor.md`: `QA agent`; absence in both protocols of `never review your own pull request`.

**Decisions:**
- The brief's values: `review level floor` from `REVIEW_LEVEL`, `auto-merge` from `AUTO_MERGE`, `tech-debt issue` from `TECH_DEBT_ISSUE`, `env-tracker issue` from `ENV_TRACKER_ISSUE`, `board scripts` from `BOARD_SCRIPTS`, `implement protocol` = `<BOARD_SCRIPTS>/../references/implement-worker-protocol.md`, `base`/`head` from `gh pr view <n> --json baseRefName,headRefOid`, `report` under the same directory as the plan-executor report.
- The "While it runs your session is busy" paragraph in Build applies to the QA agent too; say so once in Closing Artifact rather than repeating it.
- Keep the protocols' existing voice and the `{{PLACEHOLDER}}` convention for dispatcher bindings.

---

### Task 9: Recovering an owner in review, on both ticks

**Files:**
- Modify: `skills/issue-tracker/scripts/board-sweep.sh:311-392` (`pass_recover`), `:306-308` (`_recover` nudge text keyed by state)
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh` (a new `phase_review_recover` between `phase_stall` and `phase_relay`, wired into `all`)
- Modify: `skills/issue-tracker/references/execution-loop.md` and `review-loop.md` (the recovery paragraph)
- Test: `tests/issue-tracker/test-board-sweep.sh`; create `tests/claude-code/board-api/test-sweep-review-recover.sh`; `tests/claude-code/run-skill-tests.sh` lists it

**Interfaces:**
- Consumes: from Task 5 the `phase: review` meta key (the API tick's selector); from Task 1 the agent's trail (no direct read).
- Produces: nothing downstream.

**Deliverables:**
- [ ] gh: `pass_recover`'s state filter includes `in-review`; an `in-review` row with a non-reviewer name (the `_bound_rows` exclusion of `review-pr-*`/`review-epic-*` stays) takes the `in-progress|in-design` arm's decisions (`absent` → recover, `error` → recover, `idle` → recover, `live` + silent past `STALL_MIN` → recover) with the nudge text `SWEEP RECOVERY: your review of ticket #<tk>'s pull request has no live QA agent (<why>). Re-read the ticket and the PR, and if no review is running, dispatch doperpowers:qa-loop again per your protocol's Closing Artifact; if the review already reached a park or a verdict, restate it.`; the cap and park are the existing ones. Commit: `sweep: an idle owner in review is recovered like any other bound seat`
- [ ] API: `phase_review_recover` selects seat metas with `phase == "review"`, an open `run_id`, `_liveness` live, status `idle`, and parent-transcript mtime older than `STALL_MIN` minutes (reuse `_transcript_for_uuid` and `_mtime_epoch`; `BOARD_STALL_WINDOW_MIN` is not the knob — add `BOARD_REVIEW_STALL_MIN` default 45); nudges through `"$SMINOS_CLI" resume --wait "$uuid" "<the same text>"` in the background; counts in the meta key `sweep_recoveries`; at `SWEEP_RECOVERY_CAP` (default 3) parks with `BOARD_OWNER_OVERRIDE="sweep recovery: cap exhausted on bound owner $uuid (review stalled)" board-transition.sh <tk> needs-human "<note>"`. Commit: `sweep(api): recover an owner whose review stalled`
- [ ] Docs: `execution-loop.md`'s edge cases gain "Owner idle in review"; `review-loop.md`'s failure-cap section describes the owner path beside the stand-in streak.

**Tests:**
- `tests/issue-tracker/test-board-sweep.sh`: `in-review owner idle → resumed with the review nudge` (issue 61 `status:in-review`, meta `61-owner` working, FINALIZE_MAP idle → ACTION_LOG has `resume:<uuid>:SWEEP RECOVERY: your review`); `in-review owner live and silent → resumed` (stale transcript); `in-review owner live and active → untouched` (fresh transcript); `in-review owner at cap → parked needs-human` (recov=3 → board-transition to needs-human logged); `a review-pr-* seat is still excluded`.
- `tests/claude-code/board-api/test-sweep-review-recover.sh` (modelled on `test-sweep-stall.sh`'s `meta`/`say`/`SW` helpers and mock server): `idle owner with phase review and stale transcript → resume called`; `working owner → untouched`; `no phase key → untouched`; `cap → POST /tickets/<id>/transition to needs-human`.

**Decisions:**
- The gh path needs no `phase` key: `_bound_rows` already joins the seat to its ticket's state; the API path uses `phase` because the tick reads only the registry.
- Do not count nudges on the ticket; the seat meta's `sweep_recoveries` is the existing counter and the cap semantics match.

---

### Task 10: Records, version, suites, acceptance walk

**Files:**
- Modify: `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md`, `2026-07-30-implement-lane-split-design.md`, `2026-09-12-one-spec-sized-by-the-gate-design.md`, `2026-09-13-qa-loops-native-review-design.md`, `2026-09-09-review-code-lane-design.md` (each: one Revision Notes line dated 2026-09-21 naming this spec)
- Modify: `CLAUDE.md:80-81` (agents row: `qa-loop (sol/high)`; skills row: 16 skills, the review loop's references and stand-in under issue-tracker), `README.md` (any qa-loops mention)
- Modify: `docs/doperpowers/specs/2026-09-21-reviewer-fold-design.md` (Surprises from Tasks 1–9; Revision Notes)
- Run: `scripts/bump-version.sh`

**Interfaces:** consumes everything; produces the version.

**Deliverables:**
- [ ] The five revision notes, `CLAUDE.md`, `README.md`. Commit: `docs: record the Reviewer fold across the specs it supersedes`
- [ ] Every suite green: `bash tests/issue-tracker/test-board-scripts.sh`, `test-board-sweep.sh`, `test-board-gc.sh`, `test-board-surface.sh`, `test-execute-dispatch.sh`, `test-protocol-content.sh`, `test-review-dispatch.sh`, `test-bootstrap-parity.sh`, `test-review-standin.sh`, `test-qa-loop-agent.sh`; `bash tests/claude-code/run-skill-tests.sh`; `bash tests/sminos/run-sminos-tests.sh`; `python3 tests/codex/test-native-agents.py`; `bash tests/mods/run-mods-tests.sh`; `scripts/lint-shell.sh`. A failure that reproduces on `main` is recorded in the spec's Surprises, not owned.
- [ ] Acceptance items 1–10 and 12–14 of the spec executed as written, each command's output recorded in the report; a mismatch is fixed in this task when it is a slip, and returned as `BLOCKED` naming the acceptance text when the design and the code disagree.
- [ ] `scripts/bump-version.sh` to the next version above `main` (check `git show origin/main:.claude-plugin/plugin.json`), one commit: `bump: <version>`.

**Tests:** the suites above; the acceptance commands verbatim from the spec.

**Decisions:** run the suites before the bump and once after; the bump commit is last on the branch before the smokes.

---

### Task 11: Smoke on a gh-bound scratch board

**Files:**
- Create (outside the repo): a private GitHub repository `SSFSKIM/fold-smoke-<date>` with a `README.md` and one shell script to change
- Modify: `docs/doperpowers/specs/2026-09-21-reviewer-fold-design.md` (Surprises & Discoveries: the outcome, with evidence)

**Interfaces:** consumes Tasks 1–10; produces evidence.

**Deliverables:**
- [ ] Setup: `gh repo create SSFSKIM/fold-smoke-$(date +%m%d) --private --clone` into `/tmp/fold-smoke`; seed labels with `skills/issue-tracker/scripts/board-migrate-gh.sh` (read its usage first); a `.doperpowers/board.json` for the gh binding if the scripts need one (check `_binding.sh`); an open issue labeled `tech-debt`. The agent must be loadable by name: copy `agents/qa-loop.md` to `~/.claude/plugins/cache/doperpowers/doperpowers/<installed version>/agents/qa-loop.md` (the installed version from `ls ~/.claude/plugins/cache/doperpowers/doperpowers/`), and remove it at the end of this task; record in the report that this bridge was used.
- [ ] Ticket: `board-register.sh "Add a --version flag to hello.sh" enhancement P2 --state ready-for-architect --body-file <a pre-spec: purpose, acceptance (running ./hello.sh --version prints hello 1.0), decision: the flag is checked before any other argument>`.
- [ ] Dispatch from the branch worktree with `BOARD_REPO=SSFSKIM/fold-smoke-… LOCAL_REPO=/tmp/fold-smoke AUTO_MERGE_ENABLED=true REVIEW_LEVEL=low ARCHITECT_MODEL=fable skills/issue-tracker/scripts/execute-dispatch.sh <n>`; observe with `sminos list` and `board-show.sh <n>` until `done` or a park; bound the wait at 3 hours; `board-sweep.sh` may be run by hand each 30 minutes to exercise the recover pass.
- [ ] Evidence recorded in the spec's Surprises: the seat bound through `in-review` (`sminos list` output), the PR's review-trail comment naming the QA agent's rounds and the level and auto-merge value used, the merge pinned to the reviewed head, the ticket `done`; and one exercised park: before dispatch, add to the ticket body a taste fork the pre-spec leaves open (e.g., the exact wording of the version line) so the build or the review parks `needs-human`, then answer it with `board-answer.sh <n> "<answer>"` and observe the resume reaching the QA agent (its next trail line). If the panel path is not exercised because the level stayed low, run one extra `NEEDS_PANEL` drill: dispatch the QA agent by hand from a seat with `REVIEW_LEVEL=xhigh` on the merged range and observe the owner's fast-forward and the findings file hash in the trail.
- [ ] Teardown: retire the seats (`sminos retire`), remove the cache bridge, keep the scratch repository (evidence) and note its URL in the report.

**Tests:** none beyond the observed behavior; the deliverable is the recorded evidence.

**Decisions:**
- The scratch repository is the smoke's fixture; do not run the smoke on this repository's board (API-bound; Task 12).
- A failure is a finding: fix it on the branch if it is a slip in the protocols or scripts, rerun the affected step, and record both; a design disagreement is a `BLOCKED` return naming the spec text.

---

### Task 12: Smoke on this repository's API board

**Files:**
- Modify: `docs/doperpowers/specs/2026-09-21-reviewer-fold-design.md` (Surprises & Discoveries: the outcome)

**Interfaces:** consumes Task 3's deployed service and Tasks 1–10.

**Deliverables:**
- [ ] Gate: `curl -s https://arkho-board-service.onrender.com/healthz` and the service's revision or start time show a deploy after Task 3's PR merged (read the PR's merge time with `gh pr view`); if the PR is not merged, return `BLOCKED: arkho PR <url> not merged/deployed — the API smoke needs it` and stop.
- [ ] Ticket on this repository's board (`.doperpowers/board.json` is API-bound): register a small enhancement born `ready-for-architect` (a one-line doc fix in `docs/INSTALL-doperpowers.md` with a stated acceptance); dispatch with `execute-dispatch.sh --sweep` from the branch worktree (`AUTO_MERGE_ENABLED=true REVIEW_LEVEL=low`), the cache bridge from Task 11 in place; observe to `done`.
- [ ] Evidence: `board-show.sh <n>`'s timeline shows the architect run's `in-design → in-progress`, `in-progress → in-review`, a `review-trail` event, and `in-review → done` with no `release` event before `done`; the PR merged; the seat retired by the sweep's cancel pass.
- [ ] Teardown: remove the cache bridge; record the ticket and PR URLs in the report and the spec.

**Tests:** observed behavior only.

**Decisions:** the ticket's change lands on `main` through the fold itself; that is the point of the smoke. A stuck ticket is returned to the human through `needs-human` with the evidence, never force-closed.
