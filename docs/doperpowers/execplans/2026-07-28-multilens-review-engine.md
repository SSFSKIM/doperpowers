# Multi-lens review engine: let the review worker fan out 1–4 native codex reviews

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with the ExecPlan authoring rules vendored in the doperpowers plugin (skill `execplan`, `references/PLANS.md`); that file is not checked into this repository, so this document is fully self-contained.

## Purpose / Big Picture

Doperpowers' autonomous review loop (skill `skills/reviewing-prs/`) reviews every pull request with exactly one invocation of the native codex reviewer (`codex exec review`). Benchmarking on a real 22-file, +2,101-line PR showed that a single reviewer context saturates: the best single engine found 10 of 13 independently confirmed real defects, and seven differently-configured single runs each produced a *different* 8–10-item subset whose union was all 13. Coverage on large diffs therefore comes from running several differently-focused reviewers, not from any single run.

After this change, the review worker judges the diff itself and runs between one and four parallel native reviews per round: the common case stays exactly one plain run (byte-identical invocation to today), a substantial diff gets two or three, and whole-branch-scale work gets up to four. Extra runs are differentiated by a "lens" — a short, diff-derived structural focus mandate (for example "authorization and actor-identity assumptions in the changed API routes") delivered through codex's `developer_instructions` config, which the native review rubric explicitly names as an override channel. The engine still never receives ticket or spec text; work-intent reaches it the same way it always has, through committed artifacts (commit messages, code comments, AGENTS.md).

You can see it working in two ways. First, the validation milestone: on the recorded PR752 benchmark case, a lens run recovers a confirmed real defect (F3, an actor/rate-limit bypass) that the plain native review missed in two out of two recorded runs. Second, the shipped behavior: a dispatched review worker facing a large diff starts multiple background engine runs, and its review trail records the per-run findings files and the unioned triage.

This work supersedes the argus-review direction of the roadmap spec `docs/doperpowers/specs/2026-07-26-claude-review-stack-roadmap.md`: the argus (Claude-side) review engine is discarded because the native codex reviewer outperformed every Claude-side configuration on the real-PR benchmark, and multi-lens fan-out lands directly in `reviewing-prs` instead.

## Progress

- [x] (2026-07-28) ExecPlan authored after brainstorming grill; decisions settled with the human (see Decision Log).
- [ ] Milestone 1: lens validation cell on PR752 (front-loaded; its outcome gates everything after it).
- [ ] Milestone 2: `CODEX_REVIEW_LENS` passthrough in `skills/reviewing-prs/scripts/review-engine.sh` (needed by Milestone 1, so implemented first in execution order — see Plan of Work).
- [ ] Milestone 3: minimal edit to `skills/reviewing-prs/SKILL.md` (START ENGINE, JOIN, RE-REVIEW, ENGINE FALLBACK) — only if Milestone 1 passes.
- [ ] Milestone 4: reconciliation — roadmap spec revision note, board ticket parks, references check.
- [ ] Exit gate: whole-branch external review, version bump, finish/merge, retrospective.

## Surprises & Discoveries

- (seeded from the benchmark, 2026-07-28) F3 — the actor/rate-limit bypass on PR752 — was missed by both runs whose *entire* system prompt was the review rubric, and found by all five runs where review guidance rode atop a general agent scaffold, on either model family. The bare-rubric system prompt appears to narrow attention away from the authorization/actor-shape family. This is the specific blind spot the lens mechanism must be shown to recover (Milestone 1).

## Decision Log

- Decision: discard argus-review (the Claude-side review engine and its multi-agent skill) and land ensemble review as a `reviewing-prs` change using only native `codex exec review`.
  Rationale: on the real-PR benchmark the native reviewer at gpt-5.6-sol/xhigh found 10/13 vs the best Claude-side cell's 8/13; the human explicitly discarded argus. Multi-agent value survives as fan-out of the winning engine.
  Date/Author: 2026-07-28, human + session 3ca5aed9.
- Decision: the worker judges run count itself, one to four, with no numeric thresholds in the skill prose ("usually one; two or three for substantial diffs; four around whole-branch scale" is the entire calibration).
  Rationale: human's explicit instruction ("알아서 하라고 해야함; no extensive instruction"), and the repo's constraint-minimization golden rule — hard gates only for validated failure states.
  Date/Author: 2026-07-28, human.
- Decision: lenses are diff-derived structural mandates only; the engine never receives ticket or spec text. Compliance audit stays the worker's own (brief).
  Rationale: keeps the engine a pure correctness tool; the engine's observed intent-awareness already comes from committed artifacts, confirmed on PR752 (it correctly read a disclosed-limitation code comment). Confirmed with the human during the grill.
  Date/Author: 2026-07-28, human + session.
- Decision: lens transport is the `developer_instructions` config override (`-c developer_instructions=...`) riding alongside `--base`, carried by a new optional `CODEX_REVIEW_LENS` environment variable in `review-engine.sh`.
  Rationale: positional custom instructions hard-conflict with `--base` at codex's argument parser; the config override was verified live 2026-07-12 to deliver criteria into the review thread; an env var matches the script's existing `CODEX_REVIEW_MODEL`/`CODEX_REVIEW_EFFORT` pattern, so `tests/review-bench/run-case.sh` and the SKILL.md invocation shape need no structural change. Rejected alternative: a `--lens` CLI flag (more surface for the same effect). Rejected alternative: `ReviewTarget::Custom` prompt form (loses native `--base` merge-base seeding and would re-implement it by hand).
  Date/Author: 2026-07-28, session.
- Decision: validation before prose. Milestone 1 must show a lens mandate actually *shifts* the reviewer's recall profile on PR752 (concretely: recovers F3, or failing that at least one confirmed union item both plain native runs missed). If it does not, the fan-out ships nowhere: `SKILL.md` stays untouched, the engine-script change may stay (it is inert when the variable is empty), and the negative result is recorded here and in the roadmap spec.
  Rationale: only the *transport* of developer_instructions was previously proven, not its effect on recall; shipping behavior-shaping skill prose on an unproven premise violates the repo's evidence bar for skill changes.
  Date/Author: 2026-07-28, human + session (grill Question 2, "agreed").
- Decision: when fanning out, the worker typically keeps one run lens-free as the broad sweep and gives lenses to the other runs. Re-review rounds apply the same 1–4 judgment (after a small fix wave that is usually a single plain run).
  Rationale: the plain native run was the strongest single cell on the benchmark; lenses add coverage at the edges, they do not replace the sweep. One clause of guidance, no special-case machinery for re-review.
  Date/Author: 2026-07-28, session.
- Decision: simplicity-first editing of `SKILL.md` — reuse the existing block structure and sentences; the diff should read as a small amendment, not a rewrite.
  Rationale: human's explicit constraint ("과한 behavioral-influencing surface change 피하기"); skill prose is tuned behavior-shaping content.
  Date/Author: 2026-07-28, human.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

This repository is `doperpowers`, a personal fork of the `superpowers` Claude Code plugin: a set of skills (each a directory under `skills/` with a `SKILL.md`) that script how autonomous agents work. Two skills matter here.

`skills/reviewing-prs/SKILL.md` is the protocol a dispatched "review worker" follows to review one pull request unattended. Its structure is a sequence of named blocks: ORIENT (read the PR), START ENGINE (launch the reviewer), COMPLIANCE AUDIT (check the implementer against its contract while the engine runs), JOIN (collect engine output), TRIAGE (route each finding to a bin), FIX WAVES (dispatch fixer subagents), RE-REVIEW (rerun the engine after fixes, max 3 rounds), ESCALATE (merge-confidence tiers), plus AUTHORITY and REVIEW TRAIL sections. The engine is invoked as a background *tool call*, not a nested agent.

`skills/reviewing-prs/scripts/review-engine.sh` is the one engine invocation. Today it runs, from the worktree root:

    codex exec review --base "$base" -m "$model" -c "model_reasoning_effort=\"$effort\"" -c 'features.hooks=false' --json -o "$out" > "$out.events.jsonl"

with `model` defaulting to `gpt-5.6-sol` and `effort` to `xhigh` (env `CODEX_REVIEW_MODEL` / `CODEX_REVIEW_EFFORT`). The script builds a temporary `CODEX_HOME` (symlinking `auth.json`), sets `SSL_CERT_FILE` for nested runs, and adds `-c 'sandbox_mode="danger-full-access"'` only when already inside a codex sandbox (`$CODEX_SANDBOX` set — macOS cannot nest two seatbelt profiles; the outer one still confines).

"Native codex review" means the `review` subcommand of the codex CLI. Its mechanics (read from the codex-rs source, 2026-07-28): the review runs in a one-shot sub-thread whose *entire* system prompt is the 87-line review rubric (`base_instructions` is replaced); `developer_instructions` from the parent turn is stripped, but a `developer_instructions` value passed as *config* (`-c developer_instructions=...`) flows into the sub-thread as a developer message; repo `AGENTS.md` flows in as user instructions; the user turn is one sentence naming the base branch and merge-base SHA; the final message is findings JSON (title, body, confidence, priority, code_location per finding, plus an overall-correctness verdict), which `--json -o <file>` captures. The rubric itself states that more specific guidelines "in a developer message" override its general instructions — the lens channel is sanctioned by the prompt it modifies. A "lens" in this plan is a short paragraph of such guidance, derived only from the diff's structure.

The evidence base lives in `tests/review-bench/`. `run-case.sh --case <dir> --engine codex --out <file>` materializes a case into a scratch clone (for real-PR cases: clone the repo named in `case.json`, branch `main` at the recorded base SHA, branch `bench-change` at the recorded head SHA, delete the origin remote so merge-base resolution cannot escape) and runs `review-engine.sh --base main` from it. The case for this plan is `tests/review-bench/cases-real/pr752/case.json`:

    {"repo": "/Users/new/Developer/GitHub/ida-solution", "head": "624b5699a2475d25cc67dc53f061dbf0448cc16e", "base": "f7bb8b53341cf9e1f1a1227f83b077ff317812b2"}

(The local clone of `ida-solution` must exist at that path; the case is a merged PR of that repo, 22 files, +2,101 lines.)

Thirteen real defects in that PR have been independently confirmed by adjudication subagents (results and per-item key in `tests/review-bench/results/2026-07-27-pr752-modelcells/notes.md`, union items C1–C7, F1–F3, C10, N1, N2). The two recorded plain native review runs (both gpt-5.6-sol, xhigh) each found the same 10: C1 C2 C3 C4 C5 C6 C7 F1 F2 C10 — and both missed F3, N1, N2. **F3** is the validation target: in `app/api/students/promotion/route.ts` (lines ~204–207 of the PR head), the rate-limit bucket is chosen by request *shape* (`student_id` absent → narrow 5/hour self bucket) rather than by the authenticated actor, so a student who includes their own `student_id` in the body passes `assertStudentAccess` yet lands in the wide 60/hour operator bucket. Every run whose review guidance rode atop a general agent scaffold found it; both bare-rubric runs missed it.

Related state this plan touches at the edges: the roadmap spec `docs/doperpowers/specs/2026-07-26-claude-review-stack-roadmap.md` (its children C2/C3 targeted argus improvements and an argus effort ladder — now discarded; C4 was the engine-swap question — now resolved as "keep codex, fan it out"); GitHub board tickets tracking those children (find them with `gh issue list --state open` filtered by the roadmap epic #27; #30 is the known C3 ticket); and `skills/reviewing-prs/references/operation-manual.md` plus `references/review-worker-bootstrap.md`, which must be checked for sentences that assert a single-run engine.

## Plan of Work

Execution order runs the engine-script change first (Milestone 2 in numbering, first in order) because the validation cell needs it; the numbering above groups by risk instead. All work happens on the worktree branch `worktree-multilens-review-engine`; commit after each milestone.

**Engine script (`skills/reviewing-prs/scripts/review-engine.sh`).** Add an optional lens passthrough: after the `sandbox_flags` block, build `lens_flags=()`; when `CODEX_REVIEW_LENS` is non-empty, set `lens_flags=( -c "developer_instructions=$CODEX_REVIEW_LENS" )`, and include `${lens_flags[@]+"${lens_flags[@]}"}` in the `codex exec review` invocation between the `features.hooks` config and the sandbox flags. Note on quoting: codex parses the value after `key=` as TOML and falls back to the raw literal string when TOML parsing fails, so plain prose passes through unquoted; do not wrap the lens in extra TOML quotes (that would require escaping inner quotes). Update the script's header comment: the engine remains a pure correctness review that receives no ticket/spec input; `CODEX_REVIEW_LENS` optionally carries a diff-derived structural focus mandate into the review thread as a developer message, and an empty/unset variable leaves the invocation byte-identical to before. Run `scripts/lint-shell.sh` (shellcheck baseline) and confirm it passes.

**Validation cell (gates everything downstream).** From the repo root, run the PR752 case once with an actor/authz lens, capturing into a new results directory `tests/review-bench/results/2026-07-28-pr752-lenscell/`:

    CODEX_REVIEW_LENS="Focus this review on authorization and actor-identity assumptions in the changed API routes: how the acting principal is derived versus what the request body claims, and any guard, rate limit, or access-control branch whose behavior depends on request shape (which optional fields are present) rather than on the authenticated actor. Examine client-supplied identifiers that select privileged buckets or bypass narrower limits." \
    tests/review-bench/run-case.sh --case tests/review-bench/cases-real/pr752 --engine codex \
      --out tests/review-bench/results/2026-07-28-pr752-lenscell/pr752.codex-lens-authz.md

(The env var reaches `review-engine.sh` by inheritance; `run-case.sh` needs no change. The run takes roughly 10–12 minutes; use background execution with a generous timeout, as the recorded plain runs took ~670 s.) Record the lens text verbatim in the results directory's `notes.md`. Score the findings JSON against the 13-item union key in `results/2026-07-27-pr752-modelcells/notes.md`, mapping each finding to a union item by file and mechanism. PASS: the lens run reports F3 (a finding at the promotion route's rate-limit bucket selection describing the request-shape/actor mismatch) — or, failing F3 specifically, at least one confirmed union item absent from both recorded plain-native profiles (i.e. N1 or N2 or a newly adjudicated confirmed finding). FAIL: the profile is a subset of the plain profile. Either way, also record total union hits (a lens run that finds F3 but collapses to 3 total hits still passes — fan-out unions with a plain sweep — but the narrowing is worth noting for the skill prose). On FAIL: stop after committing the results; revert nothing (the engine-script change is inert when the variable is unset — decide in the Decision Log whether to keep or drop it); write the negative result into this plan, the roadmap spec's Surprises, and the final report. If the result is ambiguous (e.g. F3 absent but a plausible new finding appears), one repeat run with the same lens is authorized before judging; note both.

**Skill prose (`skills/reviewing-prs/SKILL.md`) — only after PASS.** Minimal amendment, preserving block structure and sentence style. In START ENGINE: the opening doctrine sentence currently reads "run as a PURE correctness review: it receives no criteria, no developer instructions, no ticket or spec input of any kind" — it becomes "run as a PURE correctness review: it receives no ticket or spec input of any kind" with one added sentence defining lenses: extra parallel runs may carry a lens — a structural focus mandate derived from the diff itself, passed as `CODEX_REVIEW_LENS` — and lenses never carry ticket/spec content. Step 2's single command becomes: judge the diff and choose the round's run count — most PRs need exactly one run, started exactly as today with no lens; a substantial diff may warrant two or three parallel runs, whole-branch scale up to four, each with its own `--out` file (`findings-r<N>-<k>.txt`) and, typically, one run kept lens-free as the broad sweep while the others carry lenses. Step 3/JOIN: wait for all of the round's background tasks (same 45-minute bound applies per task); the round's findings are the union of the findings files, with overlapping findings merged during TRIAGE (which already treats engine severity as a starting rank, so duplicate findings across runs simply collapse into one triaged item; keep the highest-priority duplicate as the anchor). RE-REVIEW: the same judgment applies each round — after a small fix wave one plain run is the norm. ENGINE FALLBACK gains one sentence: when at least one of a round's runs succeeds, proceed on the successful outputs and record the failed runs in the review trail; the retry/outage path applies only when the whole round fails. TRIAGE and everything downstream are otherwise untouched. Also update `review-engine.sh`'s mention in `references/operation-manual.md` and `references/review-worker-bootstrap.md` only if they assert single-run behavior (check with grep; do not restructure them).

**Reconciliation.** Append a dated entry to the roadmap spec's `## Revision Notes` (and a Decision Log line): argus-review discarded on benchmark evidence; C2/C3 rescinded; C4 resolved as multi-lens fan-out of the native engine landing in `reviewing-prs` via this ExecPlan (name this file); C5/C6 unaffected. Do not rewrite the children sections — the revision note is the record. On the board: for each open ticket implementing C2/C3-as-argus (at minimum #30), post a comment citing the evidence and this ExecPlan, then park it `needs-human` with a note recommending wontfix — closing as wontfix is the human's call, per board authority rules. Use the issue-tracker scripts (`board-transition.sh <n> needs-human "<note>"`), never raw label edits.

**Exit.** Bump the plugin version with `scripts/bump-version.sh` (minor — behavior change in a skill), run `tests/claude-code/run-skill-tests.sh` and `scripts/lint-shell.sh`, dispatch the exit-gate whole-branch review (`codex exec review --base main` from the worktree, plain, no lens), triage its findings, then finish the branch per the finishing-a-development-branch skill (merge to `main`, push). Write `Outcomes & Retrospective` here, update the roadmap spec's tracking map, and update session memory files (the multi-lens doctrine memory) to reflect what shipped.

## Concrete Steps

Working directory for all commands: the worktree root (`.claude/worktrees/multilens-review-engine` under the repo, branch `worktree-multilens-review-engine`).

1. Edit `skills/reviewing-prs/scripts/review-engine.sh` as described. Verify inertness: `bash -n skills/reviewing-prs/scripts/review-engine.sh`, then `scripts/lint-shell.sh` (expect the same pass state as before the edit). Sanity-check flag construction without a live run:

       CODEX_REVIEW_LENS="test lens" bash -x skills/reviewing-prs/scripts/review-engine.sh --base main --out /tmp/x.txt 2>&1 | grep -m1 'developer_instructions' 

   (kill it right after the grep match, or point it at a tiny scratch repo; the goal is only to see `-c developer_instructions=test lens` in the trace). Commit.
2. Run the validation cell exactly as given in Plan of Work (background, ~700 s). While it runs, prepare `tests/review-bench/results/2026-07-28-pr752-lenscell/notes.md` with the lens text and the scoring key. When it lands, score, write the verdict into notes.md and this plan's Progress/Surprises, commit. PASS → continue; FAIL → jump to step 5 with the fan-out un-shipped.
3. Edit `skills/reviewing-prs/SKILL.md` per Plan of Work (minimal diff; diff-stat should stay within roughly ±30 lines). Grep the references: `grep -rn "review-engine\|engine run\|findings-r" skills/reviewing-prs/references/` and amend only sentences that assert exactly one engine run. Commit.
4. Reconciliation edits (roadmap spec revision note; board comments + `needs-human` parks via `board-transition.sh`). Commit the spec edit.
5. `scripts/bump-version.sh` minor (skip on FAIL if nothing behavioral shipped), `tests/claude-code/run-skill-tests.sh`, exit-gate review `codex exec review --base main` from the worktree (expect a findings JSON; triage), then the finishing-a-development-branch flow: merge into `main`, push origin, remove the worktree. Fill `Outcomes & Retrospective`.

## Validation and Acceptance

Acceptance is behavioral, in three tiers. (1) Engine script: with `CODEX_REVIEW_LENS` unset, the generated codex command line is byte-identical to today's (verify via the `bash -x` trace); with it set, the trace shows the single additional `-c developer_instructions=<lens>` argument, and `scripts/lint-shell.sh` passes. (2) Lens efficacy: the PR752 lens run's findings file contains a finding locating the promotion route's rate-limit bucket selection and describing the request-shape-vs-actor flaw (F3), or another confirmed union item absent from both plain-native profiles; the scored result is committed under `tests/review-bench/results/2026-07-28-pr752-lenscell/`. (3) Skill prose: `skills/reviewing-prs/SKILL.md` reads coherently as amended — one run remains the stated norm and the command for it is unchanged; the diff against `main` stays a small amendment; `tests/claude-code/run-skill-tests.sh` passes. The exit-gate whole-branch review reports no unaddressed critical/high finding.

## Idempotence and Recovery

Every step is re-runnable. The engine-script change is inert without the env var, so a half-landed branch cannot change production review behavior. The validation cell writes to a fresh dated results directory; re-runs overwrite its files harmlessly (each run also costs ~11 minutes of gpt-5.6-sol xhigh — note repeats in `notes.md`). Board parks are idempotent via `board-transition.sh` (re-running refreshes the note). If the worktree dies mid-work, re-create it and restart from this plan's Progress section — commits are per-milestone, so at most one milestone is lost. The scratch clones `run-case.sh` creates are self-cleaning (`BENCH_KEEP=1` preserves one for postmortem).

## Artifacts and Notes

The scoring key (13-item union, PR752) lives in `tests/review-bench/results/2026-07-27-pr752-modelcells/notes.md`; the two plain-native profiles to compare against are `results/2026-07-27-realpr-r1/pr752.codex.md` (10 findings) and the model-cells notes table. Expected shape of a passing lens finding, paraphrased from the confirmed adjudication: "the promotion route derives its rate-limit bucket from whether `student_id` is present in the body rather than from the authenticated actor, so a student naming their own id passes access checks but lands in the 60/hour operator bucket, bypassing the intended 5/hour self bucket" — file `app/api/students/promotion/route.ts`, lines within ~200–210.

## Interfaces and Dependencies

`skills/reviewing-prs/scripts/review-engine.sh` keeps its exact CLI (`--base <ref> --out <file>`) and env interface `CODEX_REVIEW_MODEL` (default `gpt-5.6-sol`), `CODEX_REVIEW_EFFORT` (default `xhigh`), gaining only `CODEX_REVIEW_LENS` (default empty = today's behavior). It depends on the codex CLI ≥ the installed version (0.144+; `codex exec review` with `--json -o` and `-c developer_instructions=` config fallback-to-literal parsing). The bench depends on `jq`, `git`, and the local `ida-solution` clone at `/Users/new/Developer/GitHub/ida-solution`. Board writes go through the issue-tracker plugin scripts only. No new dependencies are introduced anywhere (the repo is zero-dependency by design).
