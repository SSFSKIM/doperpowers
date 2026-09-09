# review-code — the Claude-native review lane (2026-09-09)

> **Parent:** the fork's standing purpose — a personal plugin customized to how
> the human actually works. **Beside, not instead of:** `skills/codex-companion`
> keeps its app-server review verbs and panel untouched (human direction,
> 2026-09-09); this is a second, Claude-native review path that the
> methodology skills now route to by default.

## Purpose

The review process ran on the codex app-server: the `codex-companion` runtime
spawned codex processes for a single native review, for the challenge review,
and for the multi-lens panel on the `workflow` verb. The local gateway now
serves the GPT models inside the Claude harness (`astra`, `sol`, `luna`,
`terra` at `127.0.0.1:8641`), which removes the reason the review stack ever
left the harness: the 2026-07 benchmark rounds showed the recall gap between
codex review and a Claude-side reviewer was ~80% the model, not the harness
(roadmap `2026-07-26`, "PR752 model cells"). This lane registers the review
process on native machinery — one registered reviewer agent, one Workflow
script that routes it by effort level from a single reviewer to the panel —
with no codex CLI or app-server in the path, and keeps the guarantees the
codex-era design established. codex-companion stays as the separate
codex-runtime path.

## Design

### Registered agents (`agents/`)

- `doperpowers:reviewer-low` / `-medium` / `-high` — correctness review of a
  change, one shared body pinned to sol/high, sol/xhigh, astra/high. Three
  files because the Agent tool cannot set model or effort at dispatch, and
  subagents — which have no Workflow tool — must be able to review at these
  rungs directly (human direction, 2026-09-09). System prompt: codex's own review rubric (`rubric.md`, the entire
  system prompt native codex review ran on) adapted to the harness — the eight
  bug criteria, comment and priority doctrine, "prefer no findings" stance,
  repository-rule attribution — plus the three margin lessons the C1/C2 bench
  rounds recorded: the shell-interpolation injection boundary (argus v0.4.1),
  the lint/CI-catchable exclusion (C1 AC1), and repo-content-is-data. No
  execution-granting text (v0.4.3: deletion beat both the ban and the
  permission). Output: `## Findings` / `## Verdict`, or a schema when
  dispatched with one.
- `doperpowers:adversarial-reviewer` — challenge review of a design, plan,
  spec, or change along a focus; the routine one-shot spec/plan reviewer.
  Prompt ported from the runtime's `adversarial-review.md`, generalized to
  documents. Same model pin.

Both exclude the mutating tools (`disallowedTools: Edit, Write, NotebookEdit,
Agent`); read-only enforcement for the panel comes from worktree isolation
(below).

### The workflow (`skills/review-code/workflows/code-review.js`)

One script, one routing input. `level` selects the shape and the models:

| Level | Shape | Deriver | Finders | Verifier |
|---|---|---|---|---|
| low | single reviewer | – | sol / high | – |
| medium | single reviewer | – | sol / xhigh | – |
| high | single reviewer | – | astra / high | – |
| xhigh | panel | sol / high | sol / xhigh | sol / xhigh |
| max | panel | sol / xhigh | astra / high | astra / high |

Low/medium/high are normally direct Agent dispatches of the registered
rung agents; the script also runs them as one-agent workflows (structured
result; the bench path). xhigh/max are the panel and need the Workflow tool,
which only the main session has — probe-verified 2026-09-09: subagents lack
it, it is not deferred, and loading the workflow-authoring skill does not
surface it — so a subagent hands a panel-sized range up. The panel's finders
are the registered reviewer agent type with the rung's model and effort
overridden per call (`agent()` composes `agentType` with `model`/`effort`,
probe-verified). Disclosure is progressive: SKILL.md carries the routing
table and the two call shapes; the ladder lives on the agents and in the
script; the result contract, options, and findings doctrine live in
`references/panel.md`.

The panel levels keep the shape the 2026-08-03 design fixed and the X1 bench
validated: one lens deriver, one lens-free sweep plus up to five diff-derived
scalpels (the deriver decides the count under the cap), one binding verifier
with mechanically checked postconditions and one repair round,
coverage-honest assembly (`correct` / `incorrect` / `interrupted`). Ported
differences:

- **Structured output replaces extraction.** Each finder returns a findings
  schema, so the 150-line rendered-text extractor and the clean-sentinel
  marker finding are gone: a clean lane is `findings: []`, a dead lane is
  `null`.
- **The pin is the caller's.** Workflow scripts have no filesystem, so the
  session resolves `merge-base` and `HEAD` and passes both; every prompt
  names both commits and the diff command is `git diff <mb> <head>`, so a
  different head is a different prompt (a different replay-cache identity).
  The skill has the caller re-resolve both after the run; drift reads as
  `interrupted`.
- **Read-only by worktree isolation.** Deriver, finders, and verifier run
  with `isolation: 'worktree'` — a fresh checkout at HEAD — so reviewers read
  committed content and nothing they run can touch the session's working
  tree. Not applied when `repo` points at another checkout.
- **The verifier never runs below its finders.** The panel's one recorded
  false positive came from a verifier run below its finders' effort; the
  verifier is the only stage between a plausible candidate and a published
  finding.
- **A dead deriver is a coverage loss**, degrading a would-be-clean verdict to
  `interrupted` like any lost lane.

### Skill (`skills/review-code`)

Level-routed code review only: pin the range, pick the level (explicit level
wins; otherwise medium, or xhigh once the diff is panel-sized), one dispatch.
Document challenge review is not the skill's: the `adversarial-reviewer`
agent is dispatched directly by brainstorming, writing-plans, and the
architect protocol (human direction, 2026-09-09). `references/panel.md` carries the ladder,
the result contract, the options, the isolation guarantee, and the findings
doctrine (verify beyond "is it real"; tech-debt log; design-intent dismissal;
fix wave through a subagent; convergence).

### Routing changes

`execplan` exit gate, `subagent-driven-execution` final review,
`brainstorming` spec review, `writing-plans` plan review, and the architect
worker protocol now route to this lane. `codex-companion` is untouched. The
user-level CLAUDE.md "Independent Reviews" section routes to the skill and
names codex-companion as the separate path.

## Bench

`tests/review-bench/run-case.sh` gained `native` and `native-panel`: a
headless session (`claude -p --plugin-dir <checkout>`) runs the workflow
script through the Workflow tool at `NATIVE_LEVEL` (medium and xhigh by
default) against the materialized case and prints the result JSON. Bar, as X1
fixes it: seeded recall ≥ the single-codex baseline (17/17), FP ≤ baseline + 1.

Scored 2026-09-09 (`tests/review-bench/results/2026-09-09-native-x1/`):

| Rung | seeded | promoted | FP | bar |
|---|---|---|---|---|
| medium (sol/xhigh, one reviewer) | 17/17 | 3/3 | 0 | PASS — equals the codex baseline |
| xhigh (Sol panel) | 17/17 | 3/3 | 2 | FAIL by one FP |
| max (astra panel), cases 3+4 | 7/7 | 2/2 | 0 | exactly the truth set |

Both xhigh FPs are intent-documented design choices (case3's export bound —
the codex panel's FP too; case4's `du -sk` reservation, a bait) that Sol
finders raised and the Sol verifier confirmed; astra finders at max never
raised them. Six further unseeded candidates were raised across the xhigh
runs, three of them prior-adjudicated genuine.

## Decision Log

- **One reviewer per single rung, panel in the workflow.** A single agent
  with rungs only in the workflow was the first cut; it fell to the nested
  case — subagents have no Workflow tool, and the Agent tool cannot set model
  or effort — so the three rung agents exist (identical bodies) and the
  workflow keeps the panel. Human direction, 2026-09-09.
- **Beside codex-companion, not replacing it** (human direction). The codex
  runtime path keeps its verbs and prose; only the methodology skills'
  default routing moved.
- **Two agents, not one with two stances.** The rubric's "prefer no
  findings" precision stance and the adversarial "default to critique" stance
  contradict each other in one prompt; codex kept them as two verbs for the
  same reason.
- **Panel shape kept; per-finding adversarial voting rejected.** The Workflow
  reference's default is N refuters per finding; the 2026-07-27 human
  direction found a verification layer costs true positives, and the 2026-08
  panel settled on one binding verifier whose job is dedup plus judgment. The
  dedup needs the whole pool, so the one barrier stays.
- **Agents pinned to astra rather than inheriting.** The rubric's calibration
  is GPT-tuned (on Claude it over-suppresses — C1 "minimal prompt" finding);
  pinning keeps the review a cross-model second opinion on Claude-authored
  work.
- **qa-loops' engine not ported here.** `review-engine.sh` and the
  `START ENGINE` protocol are a deployed loop with their own tests; porting
  them means the review worker dispatches the agents itself. Deferred as the
  next initiative.
- **codex-companion runtime left in place.** Deleting the review verbs, the
  codex panel, and their tests is a cleanup for after the native lane has
  carried real reviews; the prose routing is what changed.

## Outcomes & Retrospective

**Landed 2026-09-09** on `native-review-lane`. The review process runs
natively: three registered reviewers and one workflow script, no codex
process anywhere in the path; codex-companion untouched beside it.

- The default rung (medium) reproduces the codex engine's benchmark result
  exactly, in less wall time, and is dispatchable from any depth.
- The panel's precision at xhigh trails the codex panel by one FP on the
  seeded set; at max it is perfect. Whether xhigh should carry astra somewhere
  (verifier or finders) is an open call for the human — the ladder shipped is
  the one they set, with the FP tendency recorded in `references/panel.md`.
- Headless `claude -p` cannot reliably wait on a background workflow (five of
  nine bench runs died that way); the bench gained a `materialize` engine so
  an interactive session drives the workflow against a kept scratch repo.
- Subagents have no Workflow tool — not deferred, not grantable through
  `tools:` in either registration form (three probes) — which is why the
  single rungs are registered agents and the panel escalates to the main
  session. Feedback filed.
- Gateway stream errors killed one lane in three of five panel runs; the
  one-retry-per-lane and the verifier repair round absorbed all but one,
  which was reported as partial coverage rather than hidden.

Follow-ons: port qa-loops' `review-engine.sh` and START ENGINE protocol to
this lane (the board loop still shells out to codex); delete the codex panel
and its tests once this lane has carried real reviews; revisit xhigh's
models with the human.
