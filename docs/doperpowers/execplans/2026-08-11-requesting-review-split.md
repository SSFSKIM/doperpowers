# Split codex-companion: a `requesting-review` skill, runtime fail-closed, and a script-free reviewing-prs review step

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with the vendored PLANS.md contract of the doperpowers:execplan skill (the PLANS.md file itself is not checked into this repository; this document is self-contained and does not depend on it).

## Purpose / Big Picture

Today, an agent that wants an independent code review must know about two different layers: the `doperpowers:codex-companion` skill (which documents five verbs of a vendored OpenAI Codex runtime — reviews, delegation, orchestration, job plumbing — in one place) and, inside the autonomous PR-review loop, a bash script (`skills/reviewing-prs/scripts/review-engine.sh`) that wraps the runtime and decides by a hard-coded numstat heuristic whether a diff is big enough to deserve a multi-reviewer panel instead of a single review. That script accreted real machinery: a JSON-flattening renderer, exit-code conventions, environment isolation, and a fail-closed grep for sandbox failures.

After this change, three things are true that were not before:

1. There is a new skill, `doperpowers:requesting-review`, that owns the whole *independent quality review* job: when to review, how to choose between a single native review, a steered adversarial review, and the multi-lens panel (judgment guidance with a stated default and its reason — not a script heuristic), the exact invocations, and how to read the results. Any agent — an interactive session, a dispatched review daemon, another skill — reads one skill and can request a review.
2. The vendored runtime itself fails closed on sandbox failure: a review whose probing shell never worked errors out instead of rendering a hollow "clean" verdict. That guarantee used to exist only for callers who went through `review-engine.sh`; now every consumer has it.
3. The reviewing-prs review worker routes by its own judgment following requesting-review's doctrine, invoking the runtime directly. `review-engine.sh`, `render-panel-findings.mjs`, and their test suite are deleted.

To see it working: run the test suites listed in Validation, and (the merge gate) dispatch one live review worker at a big-diff PR and observe it start the panel — not a single review, not two reviews — purely from reading its protocol.

## Progress

- [x] (2026-08-10 16:40Z) Grill complete (brainstorming session); design approved; track = autonomous.
- [x] (2026-08-10 16:55Z) ExecPlan authored and committed (b656b9de).
- [x] (2026-08-10 17:25Z) Milestone 1: runtime fail-closed — lib/sandbox.mjs; engine.mjs leaves guard via assertSandboxUsable (terminal); review AND adversarial verb branches assert on result.stderr; with-effort.mjs guards its private server's piped stderr (exit 3) since the socket path hides stderr from the verb's client; CODEX_SANDBOX stands the guard down everywhere. Tests: engine-hooks sandbox cases rewritten (fail-closed + nested-OK), fake codex gained `sandbox-broken` behavior + `-c` tolerance, 4 new runtime.test.mjs cases — all green; full companion + workflow suites green.
- [x] (2026-08-10 17:40Z) Milestone 2: skills/requesting-review/SKILL.md created; codex-companion SKILL.md verb list repointed; references/reviews.md deleted; workflows.md panel section → pointer.
- [x] (2026-08-10 17:56Z) Milestone 3: review-engine.sh, render-panel-findings.mjs, test-review-engine.sh deleted; SKILL.md START ENGINE rewritten (worker routes per requesting-review; env preamble template; findings-rN.txt/.json; interrupted retries once); ENGINE FALLBACK covers sandbox rejection + twice-interrupted panel; dispatcher binds COMPANION_DIR (3 sites); bootstrap binding renamed; operation-manual rewritten; dispatch + entrypoint suites updated and green.
- [ ] Milestone 4: consumer repoints (execplan, subagent-driven-development, writing-plans, architecting); user-CLAUDE.md repoint flagged (not edited).
- [ ] Milestone 5: full validation suites + shell lint + residual-grep sweep; version stays 7.46.0.
- [ ] Milestone 6 (merge gate): live dogfood — one dispatched review worker routes a big diff to the panel by protocol alone; PR #55 description rewritten; push.

## Surprises & Discoveries

- Observation (planning stage): the incident's sandbox markers ride the app-server child's *buffered stderr* (surfaced per turn as `result.stderr`), while the streamed progress lines also carry a truncated copy of the model's final answer — making progress a false-positive channel (a diff quoting a marker string, e.g. this repo's own tests, would trip a naive scan).
  Evidence: `skills/codex-companion/runtime/scripts/lib/workflow/engine.mjs` lines 251–265 (the buffering comment), and `executeReviewRun` in `codex-companion.mjs` returning `result.stderr` verbatim on the native-review branch.
- Observation (planning stage, CORRECTED at M1): I first noted the adversarial branch drops the turn's stderr — wrong on re-read: its payload carries `codex.stderr` (codex-companion.mjs line ~440). Both verb branches only needed the assert added.
  Evidence: `payload.codex.stderr` present in both branches; M1 diff adds only the two `assertSandboxUsable` calls.
- Observation (M1): the verb's default path and the with-effort path talk to the app-server over a socket, where the child's stderr never reaches the verb's client — `result.stderr` is populated only on the direct (dead-endpoint kill-switch) path. The guard therefore lives in THREE places: the workflow engine's leaves (disableBroker → direct), the verb branches (direct path), and with-effort.mjs itself, which pipes and scans its private server's stderr and exits 3 on a marker after a clean verb exit.
  Evidence: first new runtime test failed with exit 0 until the kill-switch env was added; with-effort test passes end-to-end against the `sandbox-broken` fake.

## Decision Log

- Decision: split codex-companion two ways (requesting-review + slimmed codex-companion), not three.
  Rationale: `review`, `adversarial-review`, and the panel are one job — independent quality scrutiny of a diff — sharing target-selection flags and output contracts; a separate adversarial-review skill would have exactly two consumers and would split the shared plumbing doc. `task`/amigo is a genuinely different job (delegation/partnership). Named by job, not runtime, so the backing engine stays swappable. Rejected: three-way split (user's original sketch; declined by user after tradeoffs); no split (leaves the discoverability problem).
  Date/Author: 2026-08-10, brainstorming session with human.
- Decision: big-diff routing moves from `review-engine.sh` to the review worker's judgment, guided by requesting-review.
  Rationale: human directive (golden rule: trust agent judgment; the pre-#55 failure was doctrine living in a doc workers never read, not judgment failing). The worker sees risk surfaces and diff character that a numstat heuristic cannot. Rejected: keep engine-internal routing (PR #55 as built — human explicitly chose against); engine survives as thin executor (once the guard moved into the runtime, nothing load-bearing remained in the script).
  Date/Author: 2026-08-10, human via AskUserQuestion.
- Decision: the fail-closed sandbox guard moves into the vendored runtime (workflow engine leaves AND the review/adversarial verb paths), exempted when `CODEX_SANDBOX` is set.
  Rationale: a clean verdict from a reviewer whose shell was broken is garbage for every consumer, not just daemons; runtime-level failure protects interactive sessions that today have no guard, and lets the script layer retire. The `CODEX_SANDBOX` exemption carries over from the engine script: under an outer codex sandbox, probe confinement is expected and the degraded diff-only render is documented behavior. Rejected: guard stays script-side (leaves interactive consumers unguarded and blocks the retirement); protocol-level grep instructions (the incident was precisely that nobody looked).
  Date/Author: 2026-08-10, human via AskUserQuestion.
- Decision: the runtime guard scans ONLY the app-server child's buffered stderr (`result.stderr` / `turn.stderr`), never `reviewText`/final-message/progress channels; ANY marker hit fails the run (no multi-hit threshold).
  Rationale: model-authored channels can quote marker strings innocently (this repo's own tests contain them), so scanning them manufactures false positives; the buffered stderr is machine-emitted. The incident showed markers on every probe, so a single-hit trigger loses nothing there, and a threshold would be an invented knob with no observed failure to calibrate against. This resolves the "sustained threshold" delegated unknown from the design.
  Date/Author: 2026-08-11, ExecPlan author.
- Decision: a marker-triggered leaf failure in the workflow engine is `terminal: true` (no transport retry).
  Rationale: a host that blocks the sandbox (userns denied) does not heal between retries; the retry would spend a full review turn to reach the same failure. The panel's own composition then yields `interrupted` (lost lane), which is the correct verdict shape.
  Date/Author: 2026-08-11, ExecPlan author.
- Decision: version stays 7.46.0; same branch, same PR (#55), description rewritten.
  Rationale: 7.46.0 was bumped on this branch and never released; the rework replaces unmerged work. Rejected: merge #55 first then follow-up (human chose same-branch rework — no interim merge of machinery about to be deleted).
  Date/Author: 2026-08-10, human via AskUserQuestion.
- Decision: the worker's per-round review environment preamble (temp `CODEX_HOME` + auth symlink, temp `CLAUDE_PLUGIN_DATA`, `SSL_CERT_FILE` bundle fallback, `CODEX_CODE_MODE_HOST_PATH` fallback) lives as an indented template inside reviewing-prs SKILL.md's START ENGINE step.
  Rationale: it is daemon-environment knowledge (outer seatbelt makes `~/.codex` read-only; nested codex cannot reach trustd), not review doctrine — so it belongs to the loop's protocol, not to requesting-review, and a helper script would resurrect the layer being retired. Rejected: dispatcher-exported env (a resumed worker whose dispatcher is gone could not recreate it).
  Date/Author: 2026-08-11, ExecPlan author.
- Decision: skill/protocol prose is authored to the root-CLAUDE.md "Authoring agent behavior" standard and the repo golden rule — generalized principles with reasons, fewest hard gates, every line earning its place; incident citations stay only where they license a hard constraint (the fail-closed guard).
  Rationale: explicit human directive at track handoff.
  Date/Author: 2026-08-11, human.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

This repository (`doperpowers`) is a Claude Code plugin: a collection of *skills* — markdown protocol documents under `skills/<name>/SKILL.md` that agents load by name — plus supporting scripts and a vendored copy of OpenAI's Codex app-server client. Everything below is relative to the repository root (the git worktree you are in).

Key parts:

- `skills/codex-companion/` — the skill wrapping the vendored Codex runtime. `SKILL.md` lists verbs; `references/reviews.md` documents the `review` and `adversarial-review` verbs; `references/workflows.md` documents the `workflow` orchestration verb and its bundled code-review panel; `references/amigo.md` (the `task` verb) and `references/jobs.md` (backgrounding) stay untouched. The runtime lives in `runtime/scripts/` — entry point `codex-companion.mjs`, app-server client `lib/codex.mjs` and `lib/app-server.mjs`, workflow engine `lib/workflow/engine.mjs`. `scripts/with-effort.mjs` wraps a verb invocation with a private app-server carrying a reasoning-effort override. `workflows/code-review.mjs` is the bundled review panel (one lens-free sweep + up to five diff-derived scalpel lenses + one binding verifier; result `{verdict, findings, coverage, lenses, explanation}` where `verdict` ∈ `correct`/`incorrect`/`interrupted`).
- `skills/reviewing-prs/` — the autonomous PR-review loop. `SKILL.md` is the pinned protocol a dispatched review daemon follows; `scripts/review-dispatch.sh` spawns workers and macro-expands `{{...}}` bindings into the protocol; `scripts/review-engine.sh` (TO BE DELETED) wraps the runtime; `scripts/render-panel-findings.mjs` (TO BE DELETED) flattens panel JSON to text; `references/operation-manual.md` and `references/runner-setup.md` are operator docs.
- `tests/` — shell/node suites: `tests/codex-companion/` (runtime; `run-codex-companion-tests.sh` and `run-workflow-tests.sh` are the runners; `mock/codex` is a scenario-driven fake codex supporting a `stderrLine` behavior that writes a line to fd 2), `tests/reviewing-prs/` (`test-review-dispatch.sh`, `test-review-engine.sh` (TO BE DELETED), `test-skill-entrypoint.sh` which asserts protocol phrases — including that `IN THE BACKGROUND` appears contiguously in START ENGINE), `scripts/lint-shell.sh` (shellcheck baseline).
- Version manifests are bumped ONLY via `scripts/bump-version.sh`; this branch already carries 7.46.0 and keeps it.

Terms: a *sandbox-failure marker* is any of the three substrings `RTM_NEWADDR`, `shell is unavailable`, `fs sandbox helper failed` appearing in the Codex app-server child's stderr — the observed signature (ida-worker-1, 2026-08-09) of a host whose filesystem sandbox never worked while codex still exited 0 and rendered findings (22 consecutive false-clean runs). *Fail closed* means: on that signature, produce an error, never a verdict. `CODEX_SANDBOX` set in the environment means we are already nested under an outer codex sandbox, where probe confinement is expected — the guard stands down there.

The current state to build from: PR #55's branch, where `review-engine.sh` contains the numstat panel routing (lines 123–157), `engine.mjs` lines 251–265 forward sandbox markers from buffered leaf stderr as `sandbox-diagnostic` events (emission only — no failure), and reviewing-prs SKILL.md's START ENGINE step tells the worker "Diff-size scaling is the ENGINE's, not yours".

## Plan of Work

Milestone 1 — runtime fail-closed. Create `skills/codex-companion/runtime/scripts/lib/sandbox.mjs` exporting the marker regex and `assertSandboxUsable(label, stderr, {onDiagnostic})`: scans buffered stderr line-by-line; every hit line is reported through `onDiagnostic` first (so journaling survives the throw); on a hit, when `process.env.CODEX_SANDBOX` is set report only, otherwise throw an Error naming the guard (`sandbox unavailable during <label>: <line> — findings would be untrustworthy`) carrying `terminal: true`. In `lib/workflow/engine.mjs`, replace the local `SANDBOX_FAILURE_MARKERS`/`emitSandboxDiagnostics` pair with the shared module: each leaf (agent turn, repair turn, review) calls the assert BEFORE `assertTurnUsable`, with `onDiagnostic` emitting the existing `sandbox-diagnostic <label>: <line>` journal event. In `codex-companion.mjs` `executeReviewRun`: the native-review branch asserts on `result.stderr` after `runAppServerReview`; the adversarial branch must first carry the turn's stderr into its result (it currently drops it), then assert the same way. The `task` verb is out of scope (delegation, not verdict-bearing). Tests: `tests/codex-companion/test-engine-hooks.mjs` — the existing sandbox-diag case now expects leaf FAILURE (and a `CODEX_SANDBOX=1` variant expects success with the diagnostic journaled); `tests/codex-companion/test-verb-e2e.sh` — a `stderrLine` marker scenario on `review` and on `adversarial-review` expects nonzero exit and the guard's message on stderr.

Milestone 2 — the requesting-review skill. Create `skills/requesting-review/SKILL.md` (frontmatter name `requesting-review`; description states triggers only: requesting an independent code review, a second opinion, an adversarial challenge of a design or plan diff, or a multi-reviewer panel on a big diff). Body: the env-contract header mirrored from codex-companion with a change-both note; routing doctrine as judgment guidance (single native review is the default; at roughly 20+ files or a couple thousand changed lines one reviewer's recall thins — the PR752 benchmark: best single run found 10 of 13 confirmed defects, seven runs' union found all 13 — so run the panel; weight concentrated on declared risk surfaces can justify the panel below that size; `adversarial-review` when the question is the design, not defects); the three invocation shapes with sibling-path runtime references (`<skill-base>/../codex-companion/runtime/scripts/codex-companion.mjs`, `with-effort.mjs` for single-review effort, the panel via `workflow --script <skill-base>/../codex-companion/workflows/code-review.mjs`); the output-reading contract (findings stdout-only, `2>` an events log; panel stdout is one JSON object whose `result.verdict` of `interrupted` is an engine failure — retry once, then treat as outage; don't commit to the branch under review while a panel round runs). Slim codex-companion: delete `references/reviews.md`; in `SKILL.md`, replace the `review`/`adversarial-review` verb lines with one pointer line to `doperpowers:requesting-review` (the verbs still exist in the runtime; this skill just no longer documents driving them); in `references/workflows.md`, replace the bundled-panel section body with a pointer to requesting-review.

Milestone 3 — reviewing-prs. Delete `scripts/review-engine.sh`, `scripts/render-panel-findings.mjs`, `tests/reviewing-prs/test-review-engine.sh`. In `scripts/review-dispatch.sh`, replace the `REVIEW_ENGINE` binding with `COMPANION_DIR` (absolute path `$SCRIPT_DIR/../../codex-companion`) at every prompt-build site (grep for `REVIEW_ENGINE`) and keep `CODEX_REVIEW_MODEL`/`CODEX_REVIEW_EFFORT` bindings. Rewrite SKILL.md's START ENGINE: step 2 keeps "the round's ONE review run IN THE BACKGROUND" (phrase `IN THE BACKGROUND` contiguous — test contract) but the worker first chooses the route by requesting-review's doctrine (the numbers and the risk-surface judgment live there; reviewing-prs states the ownership and points), then runs the chosen invocation from an indented command template: a per-round env preamble (mktemp CODEX_HOME with `auth.json` symlink, temp `CLAUDE_PLUGIN_DATA`, `SSL_CERT_FILE` bundle fallback, `CODEX_CODE_MODE_HOST_PATH` fallback — carried over verbatim from the deleted engine with their reasons) followed by either the `with-effort.mjs … review --base origin/{{BASE_REF}}` form writing `findings-rN.txt`, or the panel form writing `findings-rN.json` (raw workflow stdout). JOIN reads text or JSON accordingly; a panel `verdict` of `interrupted` retries once within the round before the ENGINE FALLBACK path. Remove every `CODEX_REVIEW_PANEL` and `CODEX_REVIEW_LENS` mention (lenses were engine plumbing; the worker never authored them). REVIEW TRAIL: panel rounds record the verdict line and lens/coverage summary from `findings-rN.json`. Update `references/operation-manual.md` (engine section → the worker drives requesting-review; pieces-table rows for the deleted scripts) and `references/runner-setup.md` if it names the engine. Update `tests/reviewing-prs/test-review-dispatch.sh` (engine-path assertions → COMPANION_DIR assertions) and `test-skill-entrypoint.sh` (drop engine-script phrase asserts, keep IN THE BACKGROUND, add a `requesting-review` pointer assert).

Milestone 4 — consumers. In `skills/execplan/SKILL.md` (exit gate) and `skills/subagent-driven-development/SKILL.md` (reviewer step): "codex native review via doperpowers:codex-companion's `review` verb" → "an independent review via doperpowers:requesting-review". In `skills/writing-plans/SKILL.md` (plan review) and `skills/architecting/SKILL.md`: the adversarial-review call-sites likewise point at requesting-review (keeping model/effort specifics). `skills/brainstorming/SKILL.md` keeps its `task`-verb pointer to codex-companion untouched. Do NOT edit the user's global `~/.claude/CLAUDE.md`; flag its "Independent Reviews" section repoint in the final report.

Milestone 5 — validation (commands below) and a residual-grep sweep: `grep -rn "review-engine\|render-panel-findings\|CODEX_REVIEW_PANEL\|references/reviews.md" skills/ tests/` must return nothing; `docs/doperpowers/{plans,specs,execplans}` history is allowed to mention them.

Milestone 6 — merge gate. Dispatch one live review worker (via `review-dispatch.sh`, auto-merge OFF, against a real big-diff PR — this branch's own PR #55 diff qualifies) and observe from its transcript that START ENGINE chose the panel by protocol alone. Rewrite the PR #55 description to describe the split (not the retired engine routing). Push.

## Concrete Steps

All commands run from the repository root.

Runtime and workflow suites:

    tests/codex-companion/run-codex-companion-tests.sh
    tests/codex-companion/run-workflow-tests.sh
    node --test tests/codex-companion/test-engine-hooks.mjs
    tests/codex-companion/test-verb-e2e.sh

reviewing-prs suites (after Milestone 3):

    tests/reviewing-prs/test-review-dispatch.sh
    tests/reviewing-prs/test-skill-entrypoint.sh

Shell lint:

    scripts/lint-shell.sh

Expected: every suite prints its pass count and exits 0; test-engine-hooks gains two case variants (marker → leaf fails terminally; marker under CODEX_SANDBOX=1 → leaf succeeds, diagnostic journaled); test-verb-e2e gains the review/adversarial marker cases (nonzero exit, guard message names the marker line).

Dogfood (Milestone 6): dispatch per `references/operation-manual.md` against a PR whose diff exceeds ~20 files; watch the worker's transcript for a `workflow --script .../code-review.mjs` invocation in START ENGINE and a findings-rN.json read at JOIN.

## Validation and Acceptance

Acceptance is behavior: (1) a `tests/codex-companion/mock/codex` scenario with `stderrLine: "bwrap: loopback: Failed RTM_NEWADDR"` on a `review` verb run exits nonzero and prints the guard's named error — before this change it exits 0 and renders findings. (2) The same scenario with `CODEX_SANDBOX=1` in the environment exits 0 (degraded-but-documented nested behavior). (3) A workflow panel run whose sweep leaf sees the marker ends with `verdict: "interrupted"`, never `correct`. (4) `skills/requesting-review/SKILL.md` exists and `skills/codex-companion/references/reviews.md` does not. (5) A dispatched review worker's prompt (test-review-dispatch fixture output) binds `COMPANION_DIR` and no longer names `review-engine.sh`. (6) All suites in Concrete Steps green. (7) Live dogfood: one dispatched worker on a big diff starts the panel by protocol alone.

## Idempotence and Recovery

Every step is a git-tracked edit on branch `worktree-review-engine-panel-routing`; re-running an edit is a no-op or a visible conflict, and `git status` plus this Progress section recover the position after any interruption. Deletions are plain `git rm` — recoverable from history. The dogfood dispatch runs with auto-merge off (observation only) so the reviewed PR cannot be merged by the worker. Commit at every milestone boundary.

## Artifacts and Notes

Deleted-line budget for orientation: review-engine.sh (182 lines), render-panel-findings.mjs (~74), test-review-engine.sh (~384). The panel result contract, for JOIN's reader: stdout JSON `{runId, result: {verdict, findings: [{id, priority, title, file, lines, comment, sources}], coverage: [{finder, status}], lenses, explanation}, agents, durationMs}`.

## Interfaces and Dependencies

In `skills/codex-companion/runtime/scripts/lib/sandbox.mjs`, define and export:

    export const SANDBOX_FAILURE_MARKERS = /RTM_NEWADDR|shell is unavailable|fs sandbox helper failed/;
    export function sandboxFailureLines(stderr)      // string -> string[] (matching lines)
    export function assertSandboxUsable(label, stderr, { onDiagnostic } = {})
    // reports every hit line through onDiagnostic, then throws Error{terminal:true}
    // unless process.env.CODEX_SANDBOX is set.

Consumers: `lib/workflow/engine.mjs` (agent leaf, repair turn, review leaf — onDiagnostic emits `sandbox-diagnostic <label>: <line>`), `codex-companion.mjs` `executeReviewRun` (both branches; onDiagnostic writes to the progress stream). No other module changes its exports. The reviewing-prs protocol depends on: `{{COMPANION_DIR}}` (absolute path binding from review-dispatch.sh), `{{CODEX_REVIEW_MODEL}}`, `{{CODEX_REVIEW_EFFORT}}` — all dispatcher-provided; and on doperpowers:requesting-review for doctrine, which depends on the sibling directory layout `skills/requesting-review` ↔ `skills/codex-companion` (both installed from the same plugin, so the layout is guaranteed).

## Revision Notes

- 2026-08-11: Initial authoring after the brainstorming grill. The "sustained threshold" delegated unknown is resolved here (stderr-only scan, single-hit trigger — see Decision Log) rather than left to implementation, since the channel analysis that settles it was done during planning.
