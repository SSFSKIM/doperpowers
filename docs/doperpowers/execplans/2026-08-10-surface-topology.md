# Surface topology: seams as first-class board objects

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up
to date as work proceeds. It is maintained per the requirements in
`/Users/new/.claude/plugins/cache/doperpowers/doperpowers/7.38.2/skills/execplan/references/PLANS.md`
(PLANS.md is not checked into this repo; its rules are restated here where
they matter: self-contained, novice-guiding, outcome-focused, living).

The approved design contract is `docs/doperpowers/specs/2026-08-10-surface-topology-design.md`
(checked in at repo root — read it before changing anything this plan says;
where the two disagree, the spec wins and the disagreement goes in the
Decision Log).

## Purpose / Big Picture

The doperpowers issue-tracker runs a ticket board on GitHub Issues: states
are `status:*` labels, typed edges live in a script-owned `<!-- board:meta -->`
HTML comment at the tail of each issue body, and a cron "sweep" dispatches
autonomous workers onto eligible tickets. A 2026-08-10 audit of a consumer
board (ida-solution) found seven open tickets all rewriting one SQL
function's body in parallel; the rewrites silently reverted each other
(different files, zero git conflicts). The board had no way to represent
"these tickets touch the same code seam".

After this change, a consumer repo can check in `.doperpowers/surfaces.md`
naming its contested surfaces. Tickets matching a surface (by declared hint,
by title/body identifier, or by PR diff) get a managed `surface:<name>`
label; the dispatcher then refuses to run two implement workers on one
surface at once (visible as a logged skip: `surface <name> occupied by #<n>
— queued`); the sweep labels tickets from PR diffs and auto-registers a
consolidation ticket when three pile up on one surface; lint rejects
invented `surface:*` labels. A repo without `surfaces.md` sees zero behavior
change — that inertness is itself an acceptance criterion.

## Progress

- [x] (2026-08-10) Spec approved (v2, independent-review revision), worktree
      created (`worktree-surface-topology`), scripts and test harness read,
      this plan authored.
- [x] (2026-08-10 ~11:00Z) M1: registry parsing + surface helpers in
      `_board.py`, `board-surface.sh` verb, snapshot `surfaces` key, lint
      vocabulary FAILs + queue report — 13 assertions green on first run.
- [x] (2026-08-10 ~11:20Z) M2: register-time matching (labels ride the
      create call, auto-relate ≤8 + mate print), transition-time re-match
      on lane entry — suite at 25 assertions.
- [x] (2026-08-10 ~11:45Z) M3: dispatch serialization — `_ticket_exports`
      surfaces/occupancy (board ∪ registry ∪ in-tick claims), lane rules,
      SURFACE_OVERRIDE — 13 new dispatcher assertions.
- [x] (2026-08-10 ~12:10Z) M4: sweep SURFACE pass (PR-diff add-only
      labeling, relates backstop capped 8/tick, consolidation
      auto-register with structural dedupe) + mock-gh
      `pr view --json files` — suite at 35 assertions.
- [x] (2026-08-10 ~12:20Z) M5: SKILL.md (toolkit row + Surfaces section +
      tripwire cross-ref), all suites green, changed-file shellcheck clean.
- [x] (2026-08-10 ~13:30Z) Exit gate round 1: codex whole-branch review
      (gpt-5.6-sol) returned 8 findings (P1 x4, P2 x4) — all adopted (see
      Decision Log); suites re-green at 38 + 14 surface assertions.
- [x] (2026-08-10 ~14:15Z) Exit gate round 2: codex re-review returned 5
      findings (P1 x3, P2 x2) — all adopted (lock held through bind;
      register relate writes under the same locks; --slurp pagination;
      stderr notices; contention-bypass logging). Suites re-green.
- [x] (2026-08-10 ~14:30Z) PR opened against main (human review gate —
      never merged by this plan). Round-2 fix delta left to the human
      gate + hermetic suites (diminishing returns on a third round;
      recorded in the Decision Log).

## Surprises & Discoveries

- Observation: the register script's output contract ("prints `<number>
  <url>`") is positional — surface mate reports printed BEFORE it broke
  `${out%% *}` parsing in the suite immediately.
  Evidence: T5 first run extracted `n2="surface"`. Fixed by printing the
  number/url line first; consumers keep their first-token parse.
- Observation: the in-tick claim set is nearly unreachable in tests — the
  stub spawn writes a working registry meta, so the registry arm names the
  fresh spawn before the claim set is consulted. The claim set survives as
  the belt for a crashed meta write.
  Evidence: T12's block reason reads `occupied by #20`, not "an earlier
  dispatch this tick".
- Observation: the queue-depth watch fired "early" during test staging —
  by T16 the suite had already accumulated 3 open members, so the
  consolidation registered one sweep before the test expected it. Not a
  defect (the threshold is global state, not per-scenario); the suite now
  parks members to stay under threshold until T18.

## Decision Log

- Decision: registry ref resolution = `SURFACES_REF` env override (tests),
  else `refs/remotes/origin/HEAD` resolved via `git symbolic-ref`, else
  `origin/main` then `origin/master` probed via `git rev-parse --verify`;
  file read with `git show <ref>:.doperpowers/surfaces.md`; any failure →
  registry None → all surface features inert.
  Rationale: spec pins entries to the default branch (human gate); tests and
  detached fixtures need an explicit override; inert-on-failure preserves
  acceptance 9. Date/Author: 2026-08-10, plan author.
- Decision: register-time auto-relate applies the same live-worker deferral
  rule as the sweep (skip a label-mate whose bound daemon is working or
  blocked; the sweep adds the edge later).
  Rationale: the spec states the deferral rule for the sweep only, but the
  hazard (full-body read-modify-write racing a live worker's own meta write)
  is identical at register time; the sweep is the sanctioned backstop for
  deferred edges, so nothing is lost. Date/Author: 2026-08-10, plan author.
- Decision: surface labels are excluded from the snapshot's leftover
  `labels` list (like `status:`/`priority:`) and carried in a new
  `surfaces` key.
  Rationale: every existing consumer of `labels` (engine routing, category
  fallback) treats it as "unmanaged labels"; a managed prefix leaking in
  would be the only exception. Date/Author: 2026-08-10, plan author.
- Decision: occupancy's registry arm excludes reviewer/lander species
  (`review-pr-*`, `review-epic-*`, `land-pr-*` metas), same exclusion as
  `_slots_used`.
  Rationale: a review worker binds the ticket it reviews; its ticket is
  already `in-review` (the board-state arm sees it), and counting the meta
  too would double-count without adding safety. Date/Author: 2026-08-10.
- Decision: consolidation ticket is registered with category `enhancement`,
  priority P1, `--state ready-for-architect`, and gets its surface label
  applied immediately after creation through the shared lib.
  Rationale: the label is the structural dedupe key — without it the next
  tick re-registers; priority P1 because a full queue is blocked behind it.
  Date/Author: 2026-08-10.
- Decision: lint's drift WARN checks only tickets that carry a surface label
  AND have linked PRs, fetching each PR's file list once.
  Rationale: bounded by the labeled set (small by construction — labels are
  incident-born); a full-board diff sweep in lint would be quota-hostile.
  Date/Author: 2026-08-10.
- Decision: the dispatch guard sits AFTER lane cap checks and BEFORE the
  parent-pin stamp, and a surface skip returns 0 (like a cap skip), not an
  error.
  Rationale: pin-stamping a ticket we then refuse to dispatch would be a
  wasted body write; a skip is normal scheduling, not a failure — the sweep
  must keep walking the list. Date/Author: 2026-08-10, plan author.
- Decision: pass_surface derives "open PRs of open tickets" from the
  snapshot's `prs` field (state OPEN) rather than a separate PR list query.
  Rationale: the snapshot already carries linked PRs per ticket; a separate
  `gh pr list` would re-fetch the same facts and see unlinked PRs the pass
  cannot act on anyway (no ticket to label). Date/Author: 2026-08-10,
  plan author.

- Decision (codex round 1, all 8 findings adopted): per-surface mkdir
  locks under `$DAEMON_HOME/surface-locks/` — the dispatcher holds a
  ticket's surface locks from the occupancy check (now a fresh-snapshot
  helper run UNDER the lock) through the spawn, and the sweep's relates
  read-modify-writes take the same lock. One mechanism closes both the
  cross-process double-dispatch window (the in-tick claim set only covers
  one process) and the relates-vs-dispatch TOCTOU. Same stale-steal
  policy as the review dispatch lock. On lock contention an implementer
  queues; the architect proceeds unlocked (never-blocked doctrine
  outranks lock hygiene for the resolver).
  Rationale: codex P1 x2; precedent in review-dispatch (#49).
  Date/Author: 2026-08-10.
- Decision (codex round 1): `surfaces_registry()` best-effort-fetches the
  default branch (30s timeout, offline degrades to the cached ref) except
  under `$SURFACES_REF`; consolidation dedupe covers arch states OR an
  open epic-with-children (decompose moves the consolidation to
  `ready-for-implementer` while members stay open); dispatch gates
  `T_SURFACES` on a loaded registry (leftover labels in a registry-less
  repo must stay inert); the consolidation label rides `--surface` on the
  register call (atomic with create); PR files come from REST
  `pulls/N/files` so `previous_filename` catches renames; relates edges
  repair per SIDE (one-sided edges from a crashed tick converge); and the
  queue-depth members count parks except `deferred` (the #52 finding-5
  twin — a parked rewrite resumes without re-running any search).
  Date/Author: 2026-08-10.

- Decision (codex round 2, all 5 adopted): the surface lock is held
  through board-bind (a spawn-time meta carries no ticket field — the
  registry arm is blind to it, so releasing at spawn reopened the
  window); register-time relate writes take the same locks with a fresh
  under-lock liveness check, deferring to the sweep on contention; PR
  file reads use `--paginate --slurp` (multi-page diffs were concatenated
  arrays json.loads rejected — a silent serialization bypass); notices
  moved to stderr to keep the `<number> <url>` stdout contract; the
  override/architect path logs when it proceeds past a contended lock.
  A third review round was deliberately not run: two full rounds were
  adopted in full, the round-2 delta is narrow, and the PR's human gate
  plus the hermetic suites own the residual. Date/Author: 2026-08-10.

## Outcomes & Retrospective

Delivered M1–M5 end-to-end on branch `worktree-surface-topology`; PR
opened against main and left unmerged (the human gate). Spec acceptance
1–9 are covered by 38 assertions in
`tests/issue-tracker/test-board-surface.sh` plus 14 surface assertions in
`tests/implementing/test-implement-dispatch.sh`; the pre-existing
issue-tracker/implementing/board-api suites pass unchanged, and the
changed file set is shellcheck-clean. Acceptance 10 (ida seed +
migration) is the planned follow-up outside this repo. Two external codex
review rounds (gpt-5.6-sol) produced 13 findings, all adopted — the
recurring lesson: every serious finding was a WINDOW (spawn-to-bind,
check-outside-lock, snapshot-to-write, page-to-page), and the fix that
held was always "do the check under the same lock the writer holds", not
a wider snapshot. The mock-gh harness absorbed every new verb (REST
files, --slurp) in ~15 lines each — that investment keeps paying.
Gap carried forward: mechanical detection of NEW contested seams stays
with the #52 prompt policy by design (spec Scope boundary).

## Context and Orientation

All paths are repo-relative in the worktree
`/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/surface-topology`.

- `skills/issue-tracker/scripts/_board.py` — the shared Python module every
  board verb runs through (via `_py` in `_lib.sh`). Owns the GraphQL
  snapshot (`snapshot()` → dict keyed by issue number as string, each node
  carrying `state`, `status_labels`, `category`, `labels` (unmanaged only),
  `prs` (linked PRs with state), `parent`, `body`, …), label management
  (`ensure_labels`, `edit_labels`), meta read/write (`parse_meta`,
  `update_meta` — a full-body read-modify-write), and the eligibility
  predicate `eligible()`.
- `skills/issue-tracker/scripts/board-register.sh` — creates the issue with
  `gh issue create --label <category>,<status:*>,<priority:*>`; gh-mode body
  is assembled in an inline `_py` heredoc.
- `skills/issue-tracker/scripts/board-transition.sh` — state changes; the
  gh-mode path also runs through an inline `_py` heredoc.
- `skills/issue-tracker/scripts/board-lint.sh` — read-only invariant checks,
  `FAIL`+`FIX:` / `WARN` lines, exit 1 on any FAIL.
- `skills/implementing/scripts/implement-dispatch.sh` — the dispatcher.
  gh-mode entry points: triggered (`implement-dispatch.sh <n>`) and sweep
  (`--sweep`), both funneling into `dispatch_one()`. `_ticket_exports`
  shell-quotes board facts for one ticket; `_slots_used` counts lane slots
  registry-first. The registry is `$DAEMON_HOME/*.json` metas with `ticket`,
  `status` (working/blocked/error/idle), `name`.
- `skills/issue-tracker/scripts/board-sweep.sh` — the cron tick; passes run
  in sequence at the file's tail (RECOVER, CANCEL, FINALIZE, IMPACT, then
  `$IMPLEMENT_DISPATCH_CMD --sweep`, review, RELAY, REPORT).
- Tests: `tests/issue-tracker/test-board-scripts.sh` + `test-board-sweep.sh`
  run the real scripts against a PATH-shimmed `tests/issue-tracker/mock-gh/gh`
  that keeps issue state in `$MOCK_GH_STATE` (JSON) and serves the snapshot
  GraphQL query. `tests/implementing/test-implement-dispatch.sh` covers the
  dispatcher with the same mock plus a stub `daemon-spawn.sh`.
  `scripts/lint-shell.sh` is the shellcheck gate.

A "surface" is a named code seam a consumer repo declares in
`.doperpowers/surfaces.md` (format in the spec: `## <kebab-name>` heading,
`- paths:` comma-separated globs, `- identifiers:` whole-word strings,
`- born-of:`, `- note:`). The board represents a surface on a ticket as a
managed label `surface:<name>`.

## Plan of Work

Milestone 1 — registry + verb + lint vocabulary. In `_board.py` add
`SURFACE_PREFIX = "surface:"`; parse surface labels into a `surfaces` node
key (and exclude them from leftover `labels`); add `surfaces_registry()`
(resolve ref per Decision Log, `git show` the file, parse to
`{name: {paths, identifiers, born_of, note}}`, return `None` when absent —
callers treat None as "feature off"), `match_identifiers(registry, text)`
(case-sensitive `\b<identifier>\b` regex), `match_paths(registry, paths)`
(fnmatch-style with `*` not crossing `/`, `**` crossing), and
`ensure_surface_label(name)` / `surface_label_add/remove` wrappers over
`edit_labels`. New verb `skills/issue-tracker/scripts/board-surface.sh
<n> --add <name> | --remove <name>`: `--add` validates the name against the
registry (die when unknown or registry absent), `--remove` never validates
(it is the orphan-cleanup path); both print `#<n>: surface +=/-= <name>`.
gh-mode only (`_refuse_no_api_route`). In `board-lint.sh` add: FAIL for any
`surface:*` label not in the registry (FIX names `board-surface.sh <n>
--remove <name>` or a surfaces.md entry), FAIL for a registry entry name
that is not kebab-case ≤ 40 chars (FIX: edit the file), and a per-surface
open-queue-depth report line; when the registry is None, surface lint runs
nothing (inertness).

Milestone 2 — matching at register and transition. `board-register.sh`
gh path: accept repeatable `--surface <hint>` (path or name, optional);
before `gh issue create`, compute matched names = names whose identifiers
match title+body OR whose paths match a declared path hint OR whose name
equals a hint; ensure those labels exist and append them to the create's
`--label` argument. After create: for each matched name, list open
label-mates from the snapshot, auto-relate (check-before-write, skip mates
with a live bound worker per the Decision Log, cap 8 newest + any open
architect-lane mate), and print the mate list. `board-transition.sh` gh
path: when the target state is `ready-for-architect` or
`ready-for-implementer`, re-run `match_identifiers` on the CURRENT body and
add any missing surface labels (add-only, no relates — the sweep backstops
those).

Milestone 3 — dispatch serialization. In `implement-dispatch.sh`
`_ticket_exports`, additionally export `T_SURFACES` (space-joined names)
and, given env `T_CLAIMED` (space-joined names already claimed this tick),
`T_SURFACE_BLOCK` (the blocking surface) + `T_SURFACE_OCCUPANT` (ticket
number or `claimed-this-tick`). Occupancy per spec: another open non-epic
non-spike ticket carrying the label in state in-progress/in-review/in-design,
OR bound registry meta (working/blocked, excluding reviewer/lander species)
on such a ticket, OR the claim set. In `dispatch_one`, after the lane cap
check: if the ticket's lane is implement (role IMPLEMENT — spikes exempt)
and `T_SURFACE_BLOCK` is non-empty and `SURFACE_OVERRIDE` ≠ 1 → echo
`surface $T_SURFACE_BLOCK occupied by #$T_SURFACE_OCCUPANT — #$n queued`
and return 0; with `SURFACE_OVERRIDE=1` echo a loud override line and
proceed. On every successful non-spike dispatch append `T_SURFACES` to the
claim variable `DISPATCHED_SURFACES` (exported into `_ticket_exports` as
`T_CLAIMED`; the sweep loop shares one shell process; triggered mode passes
its own empty set). Architect dispatches are never blocked but their
surfaces are claimed.

Milestone 4 — sweep SURFACE pass. In `board-sweep.sh` define
`pass_surface()` and call it immediately BEFORE the
`$IMPLEMENT_DISPATCH_CMD --sweep` line. The pass: load the registry (None →
`log "[sweep] SURFACE: no registry — skipped"`; return). One `_py` program:
snapshot; for each OPEN ticket with OPEN linked PRs, fetch each PR's paths
(`gh pr view <num> -R <repo> --json files -q '.files[].path'` — extend
mock-gh to serve `pr view --json files` from a `pr_files` map in its state
file), match paths → labels to add (add-only; never remove); for tickets
gaining or already holding a label, add missing relates edges between
label-mates where NEITHER side has a live bound worker; then per surface
count open implement-lane tickets (state in ready-for-implementer /
in-progress / in-review, category ≠ spike, not an epic parent, not parked)
— if ≥ 3 AND no open architect-lane ticket (ready-for-architect/in-design)
carries the label, write a body file naming every member and register a
consolidation ticket via `board-register.sh "<surface> 통합 재설계 …"
enhancement P1 --state ready-for-architect --body-file …`, then apply the
surface label to it (the structural dedupe key). Log `[sweep] SURFACE: N
labeled, M consolidations`. Add lint's drift WARN here too? No — drift WARN
stays in lint (Milestone 1 scope creep guard: it lands in M4 alongside the
mock's pr-files support, as a lint addition, since both need the same mock
extension).

Milestone 5 — docs, suites, PR. `skills/issue-tracker/SKILL.md`: one
toolkit-table row for `board-surface.sh` and a short "Surfaces" paragraph
(what the label means, where the registry lives, dispatch serialization in
one sentence, the closed-vocabulary rule) — lean per the repo's
Simplicity-First golden rule. Run `tests/issue-tracker/*.sh`,
`tests/implementing/test-implement-dispatch.sh`, `scripts/lint-shell.sh`.
Commit per milestone. Exit gate: codex whole-branch review
(`doperpowers:codex-companion` review verb, `--base main`, stderr to a
scratch file), address findings, then open the PR (base main) and STOP —
merging is the human's.

## Concrete Steps

Working directory is the worktree root. After each milestone:

    tests/issue-tracker/test-board-surface.sh      # the new suite (created in M1)
    tests/issue-tracker/test-board-scripts.sh      # no regressions
    tests/implementing/test-implement-dispatch.sh  # M3 onward
    tests/issue-tracker/test-board-sweep.sh        # M4 onward
    scripts/lint-shell.sh                          # before every commit

Expected shape of a passing run: every line `  [PASS] …` and a final
`OK (N assertions)` (the suites exit non-zero and print `  [FAIL] …` with
expected/actual otherwise). Commit messages: `feat(issue-tracker): …` per
milestone; PR via `gh pr create --base main` with the spec path in the body.

## Validation and Acceptance

Each spec acceptance criterion 1–9 maps to a named test: T5 (register
auto-label + relate + print), T8 (transition re-match), T10–T13 (occupancy
incl. registry-arm and in-tick claim), T14 (architect/spike lane rules),
T16 (diff labeling add-only), T18 (consolidation exactly-once), T3+T4 (lint
vocabulary), T15 (SURFACE_OVERRIDE), T1/T9/T19 (inertness without a
registry — plus the untouched existing suites passing unchanged, which is
the stronger inertness proof). Acceptance 10 (ida migration) is explicitly
out of scope here.

## Idempotence and Recovery

Every step is a file edit plus a hermetic test run — safe to repeat. The
mock-gh state file is per-test-mktemp, never shared. If a milestone's tests
fail mid-way, the worktree branch holds the last green commit; `git status`
+ the Progress section locate the frontier. No real GitHub repo is touched
until the final `gh pr create`.

## Artifacts and Notes

Suite runs (2026-08-10, worktree root):

    tests/issue-tracker/test-board-surface.sh     → OK (35 assertions)
    tests/issue-tracker/test-board-scripts.sh     → all tests passed
    tests/issue-tracker/test-board-sweep.sh       → all tests passed
    tests/implementing/test-implement-dispatch.sh → all tests passed
                                                    (13 new surface asserts)
    tests/claude-code/board-api/test-register-transition.sh → PASS
    scripts/lint-shell.sh <changed set>           → clean (the --all
                                                    baseline's findings are
                                                    pre-existing, in files
                                                    this branch never touched)

## Interfaces and Dependencies

In `skills/issue-tracker/scripts/_board.py`, at the end of the milestone
these exist and are importable:

    SURFACE_PREFIX = "surface:"
    def surfaces_registry() -> dict | None        # None = feature off
    def match_identifiers(registry, text) -> list[str]
    def match_paths(registry, paths) -> list[str]
    def ensure_surface_label(name) -> None
    snapshot() nodes carry: "surfaces": [name, ...]

`board-surface.sh <n> --add <name> | --remove <name>` exists and is the
only sanctioned raw write path for `surface:*` labels outside the matching
moments. `SURFACES_REF` (env) overrides registry ref resolution;
`SURFACE_OVERRIDE=1` (env) bypasses the dispatch guard loudly. No new
external dependencies; python3 stdlib only (`fnmatch` NOT used — the glob
translator is hand-rolled so `*` stays within a path segment).

## Revision Notes

- 2026-08-10: authored after the grill + spec v2; milestones sized to the
  existing test harness. Outcomes updated at finish (see section).
