# Exhaustive Final QA Loop

> **Status: Deferred (2026-07-14).** Preserved for future consideration; do not begin implementation until this design is explicitly reactivated.

Add an optional, stateful final-branch quality-assurance campaign for high-risk work that needs more than one ordinary review pass. The campaign persists findings across review, fix, and re-review rounds; separates raw observations from verified defects; blocks completion on unresolved material findings; and preserves non-blocking work through explicit landing or durable routing.

## Problem

The current development tracks have strong task-level review and fresh-evidence rules, but no reusable state machine for an extended final QA campaign.

A real M5 scheduling-lifecycle session exposed the gap:

- a cross-cutting PostgreSQL lifecycle migration required multiple independent review/fix/re-review rounds before its invariants became trustworthy;
- findings accumulated across local reports under `.doperpowers/sdd/`, without stable finding identity or a reliable query for fixed, pending, duplicated, invalid, or deferred items;
- a recursively delegated review expanded to roughly 194 live or queued tasks at four to five levels of nesting, producing duplicated review work and difficult-to-account-for outputs;
- a connection interruption killed a parent fixer and its child reviewers together; only partial filesystem edits survived, while no tracker could distinguish intent, completed work, stale claims, and recoverable artifacts;
- high-severity findings, lower-severity improvements, application cutover blockers, and future-slice concerns were mixed in prose reports and manually deduplicated by the main session.

This is not a failure of `verification-before-completion`. That skill answers whether a named success claim has fresh evidence. It does not search for unknown defects, coordinate multiple review perspectives, manage a finding backlog, dispatch fix waves, or decide when repeated re-review has converged.

It is also not the same workflow as `reviewing-prs`. That skill operates an opened-PR board/daemon loop with GitHub lifecycle and landing authority. Exhaustive final QA must work before a PR exists, against a local committed branch range, and must integrate with both controlled and autonomous execution tracks.

## Goals

- Provide one reusable final-branch QA campaign for architecture, migrations, authorization, concurrency, state machines, lifecycle protocols, and other cross-cutting high-risk changes.
- Preserve campaign state under `.doperpowers/qa/` so a new session can resume without reconstructing findings from chat history.
- Give every finding stable identity, evidence, severity, confidence, disposition, ownership, fix proof, and re-review status.
- Separate coverage-first reviewer observations from verified actionable findings.
- Run bounded, planned review panels rather than uncontrolled recursive fan-out.
- Fix every in-scope verified Critical or High finding before completion.
- Route Medium and Low findings by value and scope: fix now, land independently, spawn durable work, park durably, or invalidate with evidence.
- Require one complete dry review round against the final unchanged head before declaring convergence.
- Recover honestly from killed agents, partial worktrees, stale worker reports, unavailable reviewers, and out-of-band head changes.
- Keep ordinary changes on the existing cheaper review path.
- Compose with `verification-before-completion` rather than absorbing or weakening it.

## Non-goals

- Replacing task-scoped SDD reviews.
- Replacing the ordinary final whole-branch review for routine work.
- Replacing the GitHub issue board or `reviewing-prs` workflow.
- Turning every reviewer suggestion into a project ticket.
- Requiring a pull request before QA can start.
- Allowing uncommitted working-tree state to be the campaign's review target.
- Proving the absence of every possible defect.
- Fixing all valid low-severity observations regardless of scope or value.
- Forbidding nested delegation categorically; the design makes its cost and value explicit instead.
- Treating a round limit as evidence of success.

## Terminology

### Campaign

One stateful final QA run against a branch lineage and a declared review charter.

### Review snapshot

The immutable `merge-base..HEAD` state examined by one review round. A fix wave advances the campaign head and creates a new snapshot.

### Lens

One independent review perspective, such as concurrency, authorization, data integrity, architecture, or test-oracle quality.

### Observation

A raw reviewer-reported concern. It has not yet been verified and cannot block completion or trigger a fix.

### Finding

A stable campaign entity created from one or more observations. A finding becomes actionable only after verification.

### Fix wave

One integration unit containing one or more causally related findings. Independent fix waves may run in parallel workspaces when their edit surfaces do not overlap.

### Dry round

A complete required review panel against an unchanged head that produces no newly verified blocker or `fix-now` finding.

### Durable route

A project-visible backlog destination with an owner and revisit condition. In projects using the Doperpowers GitHub board, this is a registered issue created through the issue-tracker scripts.

## Placement in the Development Lifecycle

Create a new public skill:

```text
doperpowers:exhaustive-qa
```

It owns the QA campaign and is invoked at the existing final whole-branch review seam.

```text
task implementation
→ task-scoped reviews
→ final branch review
   ├─ ordinary review when Final QA = none
   └─ exhaustive-qa when Final QA = targeted | exhaustive
→ verification-before-completion
→ finishing-a-development-branch
```

The campaign upgrades and replaces the ordinary final review for that run. The execution path must not run one ordinary broad review and then a second exhaustive broad review over the same branch.

### Plan declaration

`writing-plans` records:

```text
Final QA: none | targeted | exhaustive
QA charter: {risk surfaces, required lenses, explicit non-goals}
```

- `none` remains the default. A legacy plan or ExecPlan with no `Final QA` field is interpreted as `none` for backward compatibility.
- `targeted` uses campaign state and convergence rules with only the lenses materially relevant to the named risk.
- `exhaustive` uses every materially applicable lens from the complete review panel.
- Planning recommends a mode from risk signals, but the selected mode is explicit and auditable.
- Execution may escalate `none → targeted → exhaustive` when later discoveries justify it, recording the reason in the living spec and plan.
- Execution never silently de-escalates a declared mode.

Recommendation signals include:

- schema migrations or data transformations;
- authorization or trust-boundary changes;
- concurrent writers, locks, transactions, idempotency, or compensation;
- state machines, lifecycle transitions, and revert semantics;
- cross-module interface or ownership changes;
- high-impact operational, deployment, or rerun behavior;
- major refactors across architectural boundaries;
- persistent orchestration, worker, or recovery protocols.

These are recommendation signals, not automatic triggers.

### Execution-path integration

- **Subagent-driven development:** invoke exhaustive QA at its current final whole-branch review node.
- **ExecPlan:** use exhaustive QA as the track's single promised final branch review; do not add a second review afterward.
- **Executing plans:** add the same optional final-review handoff before branch finishing so it cannot bypass a declared campaign.
- **Manual use:** allow invocation against a committed branch range even when no plan declared it.
- **Opened PR:** optionally attach PR metadata and comments, but do not require GitHub.

For `targeted` and `exhaustive`, the living spec and plan retrospective must be written and committed before the campaign's final dry round. The dry round and final verification therefore cover that documentation commit as part of the immutable final head. `finishing-a-development-branch` consumes the converged campaign and must not create a post-QA retrospective commit. The existing post-review retrospective behavior remains unchanged for `none`.

Each execution track records the exact campaign run path in its progress ledger. Branch finishing consumes that recorded path; manual invocation may ask the tracker to locate the unique non-abandoned campaign matching the current branch lineage and head. Zero matches or multiple matches fail closed instead of guessing.

### Relationship to verification

`verification-before-completion` remains the evidence discipline for every fix claim and the final readiness claim.

Exhaustive QA:

- discovers and verifies defects;
- tracks dispositions and ownership;
- coordinates fix waves;
- decides whether the review campaign converged.

Verification:

- identifies the command or observation that proves a named claim;
- runs it freshly against the relevant code;
- inspects full output and exit status;
- permits or rejects the claim.

The QA skill invokes verification after fixes and before convergence. Verification does not own review discovery or campaign state.

## Components

### 1. `skills/exhaustive-qa/SKILL.md`

Defines activation, preflight, campaign phases, reviewer/fixer contracts, convergence, recovery, integration handoffs, and red flags.

### 2. Tracker command

A zero-dependency Python-standard-library command under the skill's `scripts/` directory mechanically manages campaign artifacts. The exact command names are implementation details, but the interface must support:

- initialize or resume a run;
- import reviewer observations;
- fingerprint and deduplicate findings;
- verify, invalidate, assign, and transition findings;
- record fix and verification evidence;
- record durable routing;
- render `BOARD.md`;
- check convergence invariants;
- finalize `FINAL.md`.

The command writes files atomically through temporary-file replacement. It rejects illegal transitions, stale head assumptions, duplicate active owners, and incomplete durable routes.

### 3. Reviewer report template

Requires coverage-first observations with concrete failure scenarios, evidence, anchors, severity estimates, confidence, violated invariants, and suggested verification. Reviewers do not filter findings merely because they seem low-severity; central intake performs ranking and disposition.

### 4. Fix-worker brief and report templates

Give each worker exact finding IDs, current head, owned edit surface, acceptance evidence, tests, and non-goals. Reports include commit or diff identity, per-finding fix evidence, fresh commands, exit status, and unresolved concerns.

### 5. Execution-skill hooks

Small integration edits connect `writing-plans`, SDD, `execplan`, `executing-plans`, and branch finishing to the shared campaign contract without duplicating its state machine.

## Campaign Artifacts

Each campaign gets a unique run directory:

```text
.doperpowers/qa/
└── {sanitized-target}-{base12}-{started-at}/
    ├── RUN.md
    ├── BOARD.md
    ├── FINAL.md                 # written only at convergence
    ├── findings/
    │   ├── QA-001.md
    │   └── QA-002.md
    ├── rounds/
    │   ├── round-001/
    │   │   ├── correctness.md
    │   │   ├── architecture.md
    │   │   └── concurrency.md
    │   └── round-002/
    └── fixes/
        └── wave-001/
            ├── brief.md
            └── report.md
```

`.doperpowers/qa/` is local campaign state. It does not replace a shared team backlog.

Every machine-managed Markdown artifact begins with a frontmatter block containing one strict JSON object between `---` delimiters. JSON is valid YAML, remains readable in Markdown, and is parseable with Python's standard library; arbitrary YAML syntax is not accepted. Human-readable evidence and history follow in the Markdown body. Imported worker reports use the same constrained representation and are validated as untrusted input before any canonical state changes.

### `RUN.md`

Records:

- schema version and run ID;
- target branch and merge base;
- current campaign head and snapshot history;
- mode and QA charter;
- required lens panel;
- campaign state and current round;
- clean-round requirement;
- round safety ceiling;
- verification commands;
- durable backlog adapter;
- active reviewer and fixer assignments;
- scope-change and resume notes.

Campaign states are:

```text
initialized
→ reviewing
→ triaging
→ fixing
→ verifying
→ rereviewing
→ converged

any active state
→ needs-human
→ abandoned
```

`needs-human` is a resumable escalation state, not success and not necessarily failure.

### Finding file

Each finding is canonical in one Markdown file with structured frontmatter.

```json
{
  "id": "QA-001",
  "fingerprint": "v1:...",
  "title": "Direct lifecycle writes bypass atomic RPCs",
  "severity": "high",
  "confidence": "high",
  "state": "fixed-pending-rereview",
  "disposition": "fix-now",
  "first_seen_round": 1,
  "last_seen_round": 2,
  "source_lenses": ["security", "lifecycle"],
  "anchor": {
    "path": "sql/p106_m5p4_lifecycle_foundation.sql",
    "symbol": "agent_proposals_own_all"
  },
  "owner": "fix-wave-1",
  "scope_head": "035d06b",
  "external_ref": null
}
```

The body contains:

- violated invariant;
- concrete failure scenario;
- source observations;
- code and runtime evidence;
- verification or rebuttal record;
- chosen disposition and rationale;
- fix evidence;
- fresh verification evidence;
- re-review evidence;
- append-only transition history.

### Finding identity and deduplication

A fingerprint derives from:

- normalized violated invariant or failure mode;
- stable path and symbol/resource anchor;
- relevant operation or state transition;
- branch lineage.

Line number alone is never identity. Later observations can add evidence to an existing finding, become an explicit duplicate, or supersede an older formulation.

### Finding classification

Keep three axes separate:

- **Severity:** `critical | high | medium | low`
- **Confidence:** `high | medium | low`
- **Disposition:** `fix-now | park | spawn | invalid | duplicate | superseded`

Board priority is not technical severity. Confidence is not severity. Disposition is not severity.

### Finding lifecycle

```text
observed
  → verified
  → invalid

verified
  → fix-now
  → parked
  → spawned
  → duplicate
  → superseded

fix-now
  → claimed
  → fixing
  → fixed-pending-verification
  → fixed-pending-rereview
  → verified-fixed
```

A later round may reopen a finding when its failure scenario remains reproducible or a fix regresses.

Rules:

- Raw `observed` findings do not block and cannot be sent directly to a fixer.
- Any in-scope verified Critical or High finding blocks convergence.
- Any finding selected as `fix-now` blocks convergence regardless of severity.
- Medium and Low findings use cost-aware disposition.
- A Critical or High finding can be durably routed instead of fixed only when evidence shows it is pre-existing or outside the branch's introduced or worsened risk. That boundary claim is itself reviewed.
- `parked` and `spawned` are terminal only with a durable destination, owner, rationale, and revisit condition.

### `BOARD.md`

`BOARD.md` is a generated projection, not canonical state. It groups:

1. blockers;
2. active `fix-now` work;
3. findings awaiting verification or re-review;
4. durably parked or spawned findings;
5. invalid, duplicate, superseded, and verified-fixed findings.

If the board drifts or is truncated, regenerate it from finding files. Never reverse-import board prose into canonical finding state.

### `FINAL.md`

Written only after convergence. It records:

- immutable final head;
- base and reviewed range;
- mode and charter;
- completed lenses and reviewers;
- round and fix-wave counts;
- finding counts by severity, state, and disposition;
- all durable routes;
- fresh final verification evidence;
- the dry-round result;
- any accepted residual risk.

Branch finishing consumes this report but does not reinterpret or weaken it.

## Ownership and Concurrency

The main QA orchestrator is the sole canonical tracker writer.

Reviewers and fix workers:

- receive immutable inputs;
- return structured reports or write workspace-local reports;
- never edit `RUN.md`, canonical finding files, or `BOARD.md`;
- never declare campaign convergence.

The orchestrator validates and imports their output.

Before dispatch, the orchestrator records:

- assignment and finding IDs;
- input head;
- reviewer lens or fixer edit surface;
- workspace/worktree path when applicable;
- expected output shape;
- start time and status.

Related findings that touch the same subsystem or causal mechanism go to one omnibus fixer. Independent overlap groups may use parallel isolated workers. No two workers intentionally own the same edit surface.

Nested reviewer dispatch remains allowed when it adds a distinct perspective, tool, or context. It must be summarized by the parent and count against the round's declared reviewer budget. The design uses visibility and value judgment rather than a blanket nesting prohibition.

## Campaign Flow

### Phase 1: Preflight

Require:

- clean committed target head;
- known merge base;
- approved spec and plan when present;
- final QA mode and charter;
- task reports and existing review evidence;
- project constraints;
- final verification commands.

Build one review package outside the main session's context where practical. The package is scoped to `merge-base..HEAD` and referenced by reviewers.

If a matching unfinished campaign exists on the same branch lineage, resume it instead of creating a parallel campaign.

### Phase 2: Plan the lens panel

Typical lenses are:

- specification and domain invariants;
- correctness and edge cases;
- architecture and interface boundaries;
- security and authorization;
- data integrity and migration/rerun behavior;
- concurrency and atomicity;
- operational and deployment failure modes;
- test-oracle quality;
- simplification, duplication, and efficiency.

`targeted` selects named relevant lenses. `exhaustive` includes every materially applicable lens. A lens that has no plausible relationship to the change is explicitly marked not applicable rather than run mechanically.

### Phase 3: Dispatch read-only reviewers

Reviewers receive the same immutable package plus their lens-specific charter. They report every concrete concern, including uncertain and lower-severity observations, with confidence and severity estimates. They do not mutate code or the tracker.

The panel is planned and bounded. The main orchestrator owns coverage and deduplication.

### Phase 4: Verify and deduplicate observations

For every observation:

1. derive or match a fingerprint;
2. inspect the cited code and assumptions;
3. reproduce or otherwise verify the failure when feasible;
4. dispatch a targeted independent verifier for disputed or high-impact claims when useful;
5. record invalid findings with rebuttal evidence;
6. promote only verified findings to disposition.

This phase prevents plausible reviewer output from becoming unexamined implementation work.

### Phase 5: Choose dispositions

- Critical and High in-scope findings are `fix-now`.
- Medium and Low findings are `fix-now` when the change is small, in-scope, low-risk, and actionworthy.
- Independent `fix-now` groups may run in isolated workers while the main orchestrator continues triage or verification.
- Large, speculative, scope-expanding, or independently valuable work is spawned or parked durably.
- Invalid, duplicate, and superseded findings retain evidence and stop consuming fix capacity.

Every disposition records rationale.

### Phase 6: Run fix waves

Each fix wave receives exact finding files and acceptance evidence. Workers use TDD where applicable, verify the amended behavior, commit or otherwise identify the result, and return per-finding proof.

The orchestrator reviews and integrates each result. A worker's claim can move a finding only to `fixed-pending-verification`.

After integration:

1. run fresh focused verification for each fix;
2. run broader affected verification when behavior or shared contracts changed;
3. advance the campaign head;
4. mark the finding `fixed-pending-rereview` only when evidence passes.

### Phase 7: Re-review

Run two complementary checks:

- a regression verifier receives prior finding history and checks every claimed fix against its original failure scenario;
- a fresh discovery panel reviews the new snapshot from the charter rather than merely confirming prior conclusions.

Verified fixes become `verified-fixed`. New verified blockers or `fix-now` findings reopen the loop.

### Phase 8: Dry round and finalization

After all findings are terminally resolved or routed, run one complete required panel against the unchanged head.

The round is dry when it produces no newly verified blocker or `fix-now` finding. New observations may still be invalidated or durably routed, but any code change invalidates the dry result and requires another round.

On a dry round, run final verification, enforce convergence invariants, write `FINAL.md`, and hand off to branch finishing.

## Interruption and Recovery

Agent messages and status text are not authoritative. Filesystem, Git, campaign artifacts, and fresh verification are authoritative.

On resume, inspect:

1. `RUN.md`, finding files, and saved round/fix reports;
2. Git status and commits in every assigned workspace;
3. live or resumable worker state;
4. whether each result still applies to the current campaign head.

A killed worker never advances a finding merely because it announced intent. Partial edits are audited before preservation. The orchestrator may resume the same worker, assign a fresh worker, import a valid partial commit, or discard stale work with a recorded reason.

### Failure rules

- **Reviewer unavailable or rate-limited:** substitute an equivalent reviewer, retry later, or mark the required lens incomplete. Do not claim exhaustive coverage for a lens that never ran.
- **Malformed or unsupported observation:** retain it as `observed` until clarified; do not block or fix it.
- **Conflicting fix workers:** stop integration, regroup the overlapping findings, and give one owner the combined fix.
- **Unexpected head change:** record a scope revision, invalidate clean status, and re-evaluate outstanding reports and worktrees.
- **Design-changing discovery:** update the living spec and plan before continuing. QA does not silently redefine behavior.
- **Missing durable route:** a parked finding remains non-terminal until a real destination exists or the disposition changes.
- **Truncated or stale board:** regenerate it from canonical finding files.

## Convergence

A campaign may mark `converged` only when all conditions hold:

1. the reviewed head is still current;
2. every in-scope verified Critical or High finding is `verified-fixed`;
3. every `fix-now` finding is `verified-fixed`;
4. every invalid finding has rebuttal evidence;
5. every parked or spawned finding has a durable destination, owner, rationale, and revisit condition;
6. no reviewer or fixer remains active against the branch;
7. every required lens completed or is explicitly not applicable;
8. fresh verification passed on the final head;
9. one complete dry round passed on that unchanged head;
10. the living spec and plan reflect every design-changing discovery.

The default safety ceiling is five review rounds. Reaching the ceiling does not pass. It moves the campaign to `needs-human` with evidence that the implementation is unstable, the design is unresolved, the charter is too broad, or the review process is failing to converge.

Other `needs-human` triggers include:

- a fundamental architecture dispute;
- a required reviewer or tool that cannot be substituted;
- a scope-changing fix that the approved design does not authorize;
- no available durable backlog route for intentionally deferred work;
- repeated fix regressions or contradictory verified findings.

## Durable Routing

The active campaign ledger is local. Findings that intentionally leave campaign scope must be promoted to the project's durable backlog.

When the project uses the Doperpowers GitHub issue board:

- invoke the issue-tracker workflow and its scripts;
- preserve category, status, parent/dependency relationships, origin campaign, source finding ID, severity, and revisit condition;
- write campaign provenance and the local `QA-NNN` finding ID into the issue body through `board-register.sh --body-file`;
- use `--spawned-by` only when an actual originating GitHub issue number exists; a local campaign or finding ID is not an issue number;
- store the resulting issue reference in the finding file.

When another durable backlog exists, store its stable reference and equivalent ownership/revisit metadata.

When no durable backlog is configured, the skill must not relabel local-only state as durable. It either fixes the finding, obtains a project-approved durable destination, or pauses in `needs-human`.

## Testing and Evaluation

### Mechanical tracker tests

Cover:

- legal and illegal transitions;
- stable ID assignment;
- fingerprint deduplication and explicit duplicates;
- board regeneration;
- blocker derivation;
- stale-head rejection;
- durable-route validation;
- dry-round convergence;
- killed-worker recovery;
- safety-ceiling escalation;
- malformed or stale worker reports;
- atomic file updates.

### Skill integration tests

Verify that:

- `writing-plans` records mode and charter;
- SDD upgrades its final review rather than running two broad reviews;
- `execplan` still performs exactly one final branch review;
- `executing-plans` cannot bypass a declared campaign;
- branch finishing rejects an incomplete campaign;
- final verification is fresh and final-head-specific;
- `Final QA: none` does not create an exhaustive tracker.

### Adversarial behavior evals

Run real harness sessions for:

1. a small ordinary change that correctly avoids exhaustive QA;
2. a targeted migration review with only relevant lenses;
3. a lifecycle/transaction change with duplicate, invalid, blocking, and non-blocking observations;
4. multiple reviewers describing the same defect differently;
5. a worker killed after partial edits but before completion;
6. an out-of-band head change during a fix wave;
7. an unavailable required reviewer;
8. an independent non-blocking fixer completing after the branch advanced;
9. no durable backlog adapter;
10. a finding that changes the approved design;
11. nested delegation expanding beyond expected value;
12. a dry round finding a new blocker and correctly reopening the loop.

Judges verify behavior rather than prose:

- no false convergence;
- no lost or silently dropped findings;
- no raw observation sent directly to a fixer;
- no duplicate broad final review;
- no silent missing lens;
- no branch finish with active workers;
- no successful park without a durable route;
- no uncontrolled review expansion without tracker-visible justification.

### Comparative metrics

Measure before and after:

- verified defect recall;
- false-positive rejection rate;
- duplicate finding rate;
- unresolved-blocker false-pass rate;
- interruption-recovery success;
- reviewer and worker counts;
- rounds, latency, token use, and cost;
- percentage of ordinary tasks that correctly avoid exhaustive QA.

Report ranges across repeated runs rather than single-run point claims.

## Rollout

1. Implement the standalone tracker and `exhaustive-qa` skill.
2. Integrate it with SDD's existing final-review seam.
3. Dogfood it on one real high-risk branch and record surprises.
4. Add `execplan` and `executing-plans` parity.
5. Add plan-time recommendation heuristics only after standalone campaign behavior is proven.
6. Keep `Final QA: none` as the default until eval evidence supports broader recommendation behavior.

## Acceptance Criteria

- When a plan declares `Final QA: none`, execution performs the ordinary final review and does not create a QA campaign.
- When a legacy plan has no `Final QA` field, execution treats it as `none`.
- When a plan declares `targeted` or `exhaustive`, execution creates or resumes one campaign and uses it as the single final branch review.
- A campaign always reviews a committed `merge-base..HEAD` snapshot, never an unstable uncommitted working tree.
- Reviewer observations receive stable identities and are deduplicated before disposition.
- An unverified observation cannot block completion or reach a fixer.
- In-scope verified Critical and High findings prevent convergence until re-reviewed as fixed.
- A selected `fix-now` finding prevents convergence regardless of severity.
- Medium and Low findings are fixed or durably routed with explicit rationale.
- Parallel fix workers never directly mutate canonical campaign state.
- A killed worker's intent does not count as progress; surviving filesystem work is audited before reuse.
- A head change invalidates prior clean status and stale worker assumptions.
- A required missing lens prevents exhaustive coverage from being claimed.
- A dry round that discovers a new material finding reopens the loop.
- Reaching the round ceiling escalates instead of passing.
- A parked or spawned finding without a durable destination prevents convergence.
- The campaign writes `FINAL.md` only after fresh final-head verification and one stable-head dry round.
- For `targeted` and `exhaustive`, the committed retrospective is part of the reviewed final head and branch finishing creates no post-QA commit.
- Branch finishing consumes the execution ledger's exact campaign path, or a unique lineage-and-head match for manual use; it fails on missing or ambiguous campaign state.
- Branch finishing does not proceed through a declared incomplete campaign.
- The new workflow does not replace or weaken `verification-before-completion`.
- Real-session evals show that routine changes avoid the exhaustive path while high-risk scenarios retain state and recover from interruption.

## Decision Log

### 2026-07-14 — Dedicated final QA skill

**Decision:** Create `doperpowers:exhaustive-qa` as a standalone stateful workflow and integrate it at the final whole-branch review seam.

**Rejected: embed the loop separately in SDD, `execplan`, and `executing-plans`.** This duplicates the state machine, prevents consistent manual invocation and resume, and invites drift between execution tracks.

**Rejected: make exhaustive QA a mode of `verification-before-completion`.** Verification proves named claims; exhaustive QA searches for unknown defects and manages remediation. The verification skill's broad trigger would also over-apply an expensive campaign.

### 2026-07-14 — Hybrid local ledger and durable backlog

**Decision:** `.doperpowers/qa/` owns active campaign state. Findings intentionally leaving the campaign must be promoted to the project's durable backlog.

**Rejected: local ledger only.** It is invisible across machines and to collaborators, and `.doperpowers/` is intentionally local working state.

**Rejected: issue tracker only.** Creating a ticket for every raw observation produces noise and makes rapid deduplication and review-round state cumbersome.

### 2026-07-14 — Separate classification axes

**Decision:** Track severity, confidence, and disposition separately.

**Rejected: one P1/P2/P3 field.** It conflates impact, certainty, urgency, cost, and chosen action.

### 2026-07-14 — Planned lens panel

**Decision:** Use a bounded, centrally coordinated panel, mostly flat, with nested delegation allowed when it adds distinct value and remains visible to the round budget.

**Rejected: one strongest reviewer only.** It provides less perspective diversity and creates a large single-context burden.

**Rejected: unconstrained reviewer-led delegation.** The p106 session demonstrated duplicate work and runaway fan-out without central accounting.

### 2026-07-14 — One stable-head dry round

**Decision:** Require one complete dry panel after all selected fixes and routes are complete.

**Rejected: two mandatory dry rounds.** A diversified panel plus regression verification makes the second clean round usually redundant and expensive.

**Rejected: fixed round count as success.** Count does not establish convergence.

### 2026-07-14 — Finding files plus generated board

**Decision:** Use one canonical Markdown file per finding, a run manifest, raw round/fix reports, and a generated board.

**Rejected: append-only JSONL as the primary interface.** It offers stronger event reconstruction but adds machinery and is harder for humans to inspect and correct during an optional local workflow.

**Rejected: one large Markdown board.** It becomes fragile and unreadable as evidence, ownership, and round history accumulate.

### 2026-07-14 — Main orchestrator is the sole tracker writer

**Decision:** Workers return reports; the main orchestrator verifies and imports state transitions.

**Rejected: direct multi-writer finding updates.** Isolated workspaces and concurrent edits create stale or conflicting campaign copies.

**Rejected for initial implementation: script-mediated distributed writes with leases.** It adds coordination machinery not justified before the single-writer workflow is proven.

### 2026-07-14 — Branch range is the primary target

**Decision:** Review a committed branch range, with optional PR metadata.

**Rejected: PR-only operation.** It duplicates `reviewing-prs` and cannot serve the pre-PR controlled track.

**Rejected: uncommitted working-tree target.** It weakens reproducibility, identity, and interruption recovery.

### 2026-07-14 — Retrospective precedes head-bound convergence

**Decision:** For `targeted` and `exhaustive`, write and commit the living spec and plan retrospective before the final dry round. Branch finishing verifies that retrospective and consumes `FINAL.md` without creating another commit.

**Rejected: keep the existing post-review retrospective commit.** It advances `HEAD` after the dry round and makes the campaign's immutable final-head evidence stale before branch finishing begins.

**Rejected: exempt documentation-only commits from stale-head checks.** The reviewed snapshot would still differ from the branch being finished, and documentation can change operational or acceptance meaning.

### 2026-07-14 — Campaign lookup fails closed

**Decision:** Execution ledgers record the exact campaign run path. Manual branch finishing may locate a campaign only when exactly one non-abandoned run matches the current branch lineage and head.

**Rejected: select the newest campaign directory.** Timestamps do not prove lineage, completeness, or applicability, and can silently choose stale state after interruption.

## Surprises & Discoveries

- `.doperpowers/` is intentionally ignored in this repository. It is suitable for resumable local execution state, not a shared team backlog.
- The current `reviewing-prs` protocol already separates reviewer severity from fix-forward routing and requires every finding to be fixed, spawned, parked, or invalidated. Exhaustive QA can reuse that conceptual split without inheriting PR/daemon lifecycle.
- `requesting-code-review` and `receiving-code-review` are no longer present on the current branch. The new skill must not depend on those historical paths.
- SDD and `execplan` already have explicit final whole-branch review seams, while `executing-plans` currently lacks equivalent final-review parity.
- Existing SDD cost evidence supports narrow task review plus one broad final review. Exhaustive QA must upgrade that one final review rather than adding broad review at every task boundary.
- Connection cancellation and agent cancellation do not imply filesystem rollback. Recovery must inspect Git and files rather than treating worker status messages as authoritative.
- The p106 fan-out incident was caused by recursive orchestration economics, not evidence of a general provider-concurrency regression. The design therefore governs review shape and visibility rather than changing a global concurrency setting.
- Existing branch finishing commits the retrospective after review. A head-bound campaign cannot preserve that order; targeted and exhaustive runs must commit the retrospective before the dry round, while `none` retains the current behavior.
- Legacy plans predate the `Final QA` field. Treating an absent declaration as `none` preserves compatibility without silently weakening any explicitly declared campaign.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-14: Resolved final-head sequencing and compatibility details discovered during implementation planning: legacy missing declarations mean `none`; targeted/exhaustive retrospectives are committed before the dry round; execution ledgers record the campaign path and ambiguous lookup fails closed; GitHub durable routes carry campaign provenance in `--body-file`, not a fabricated `--spawned-by` value.
- 2026-07-14: Constrained every machine-managed Markdown frontmatter block to one strict JSON object between `---` delimiters. This preserves the human-readable Markdown design while making parsing and validation feasible with the repository's Python-standard-library-only rule; arbitrary YAML is explicitly unsupported.
- 2026-07-14: Initial design after the M5 Phase 4 p106 multi-round review/fix session. Chose a dedicated final QA skill, local finding ledger with durable routing, planned lens panels, centralized tracker ownership, and stable-head dry-round convergence.
