# board-sync — GitHub ↔ Issue-Board Reconciler — Design

**Goal:** Keep the local issue board (`doperpowers/issue-tracker/map.json`) and a consumer repo's GitHub issues from drifting apart, automatically. `board-sync` is a registered subagent that reconciles the two on invocation or on a cron schedule: it runs a deterministic diff, applies the unambiguous changes through the existing board scripts + `gh`, and **reports conflicts instead of guessing**. The board's single-writer rule, state machine, and script-enforced invariants are untouched — board-sync writes only through them. This fills the "GitHub/GitLab sync or export" gap the substrate deferred (`2026-07-03-issue-tracker-substrate-design.md`, Out of scope).

## Problem

The board and GitHub are linked only by convention today: a ticket's GitHub issue number lives as `(GH#NN)` text inside its `title`, and the two are updated by hand, separately. They drift, and nothing detects or repairs it.

Concretely (ida-solution, 2026-07-04→05): the board sat frozen at its 2026-07-03 state while the umbrella spec and GitHub moved on — the orchestrator had materialized 21 GitHub issues (#53–#73) and re-cut priorities, but `map.json` reflected none of it, because the board update was a separate manual step that lagged. A human had to notice. The pain is bidirectional and recurring:

1. **Completion drift** — a daemon lands a ticket, the orchestrator flips the board to `done`, but the GitHub issue stays open; or an issue is closed on GitHub and the board still shows it active.
2. **No machine linkage** — the only ticket↔issue link is `(GH#NN)` parsed from title text; there is no structured field, so nothing can reliably answer "which issue is this ticket."
3. **No drift detection** — divergence is invisible until a human trips over it.

## Design Overview

board-sync is a **thin judgment layer (a subagent) over a deterministic toolkit**. It never hand-edits `map.json`; every board mutation goes through the existing invariant-enforcing scripts (`board-transition.sh`, `board-edge.sh`, and two new metadata writers), and every GitHub mutation goes through `gh`. The subagent's only job is the fraction that genuinely needs judgment — ambiguous close-reason mapping, conflict adjudication, whether an unlinked issue should even join the board. The deterministic remainder is computed and applied by scripts.

Reconciliation is **bidirectional against a last-sync watermark**. `map.json` has no per-field timestamps, so "which side changed since last time" can only be recovered by remembering the last-synced value: a `.sync-state.json` snapshot, one entry per linked ticket. On each run, per synced facet (state, labels, edges): if only one side differs from the watermark → that side changed → propagate to the other; if **both** sides differ and disagree → **true conflict** → report, never auto-resolve.

Three approaches were weighed:

- **A — self-contained subagent + deterministic toolkit** (chosen). An invocation or cron spawns the `board-sync` agent; it runs `board-gh-plan.sh`, judges the plan, applies via the scripts, updates the watermark, writes a report. Satisfies unattended cron autonomy while keeping every mutation deterministic and auditable.
- **B — no agent; the orchestrator judges.** The toolkit emits a plan and the main session applies it during `board-reconcile.sh`. Rejected: no unattended path — it needs a human session present, which is exactly the condition under which drift accumulated.
- **C — detector daemon proposes, orchestrator applies** (the existing worker/proposal model). Rejected: two-hop latency and needs the orchestrator online to apply — overkill for a mechanical reconcile that can be made deterministic.

## 1. Schema & data-model changes (issue-tracker core)

Two optional, backward-compatible node fields (a missing field = "unset", so old boards load unchanged); `map.json` `version` stays `1` — the fields are additive and readers use `.get(...)`, so there is no migration:

- **`gh`** (int | null) — the linked GitHub issue number. Sits beside the existing external refs `branch`/`pr`. This is the machine linkage; title text is never parsed again after backfill.
- **`labels`** (string[]) — the last-reconciled set of *free* GitHub labels for this ticket (see §4). Managed/derived labels (`epic`, `state:*`) are **not** stored here.

New sibling file, **`doperpowers/issue-tracker/.sync-state.json`** — the watermark. Orchestrator-only, main-checkout-only, committed (so it survives and is diffable). Per linked ticket, the last value on which board and GitHub agreed:

```json
{
  "version": 1,
  "synced_at": "2026-07-05",
  "tickets": {
    "T3":  { "gh": 27, "state": "ready-for-agent", "labels": ["priority:P0","size:M"], "blocked_by_gh": [] },
    "T26": { "gh": 68, "state": "in-progress",     "labels": ["priority:P1"],          "blocked_by_gh": [72] }
  }
}
```

A conflicted ticket keeps its **old** watermark entry (so it stays flagged every run until a human resolves it); every non-conflicted linked ticket's entry is refreshed to the post-apply agreed value at the end of a successful run.

## 2. The toolkit (`skills/issue-tracker/scripts/`)

Same house pattern as the rest of the board toolkit: bash + inline `python3` stdlib, atomic writes (tmp + `os.replace`), no deps, refuse-in-worktree guard from `_lib.sh`. **Scripts enforce invariants and determinism; the agent judges semantics.**

| script | does |
|---|---|
| `board-gh-plan.sh` | **pure diff, no mutation.** Reads `map.json`, `gh issue list --json number,state,stateReason,labels,body,title`, and `.sync-state.json`; emits a structured **plan** (JSON, stdout) — per facet: proposed action + direction + `auto` flag, or `conflict` with all three values (board / gh / watermark). Also lists `unlinked_board`, `unlinked_gh`, `orphans`. |
| `board-gh-apply.sh` | consumes a plan (or a filtered subset) and executes only `auto:true`, non-conflict actions: board side via `board-transition.sh` / `board-edge.sh` / `board-meta.sh`; GitHub side via `gh`. Supports `--dry-run` (print the exact script/`gh` calls it *would* make — the hermetic test seam). Rewrites `.sync-state.json` for reconciled tickets on success. |
| `board-meta.sh <id> [--gh N] [--add-label L] [--rm-label L]` | deterministic writer for the new node fields (`gh`, `labels[]`) — atomic, re-renders `BOARD.*`. Keeps label/link writes off the LLM's hands, same as `board-transition.sh` does for state. |
| `board-link.sh <id> --gh N` \| `--backfill` | thin front for the one-time migration: `--backfill` parses `(GH#NN)` from every ticket title once and populates `gh`, then the board never depends on title text again. (`--gh N` is sugar over `board-meta.sh`.) |

## 3. Reconcile algorithm (per run)

```
plan   = board-gh-plan.sh                      # deterministic: f(map.json, gh, watermark)
judge  = board-sync agent reads plan:
           auto:true non-conflict actions  → keep
           conflicts                       → do NOT touch; collect for report
           ambiguous (GH reopen, unlinked) → do NOT touch unattended; collect for report
apply  = board-gh-apply.sh <confirmed subset> # board via scripts, GH via gh
                                              # refresh .sync-state.json for reconciled tickets
report = write doperpowers/issue-tracker/SYNC-REPORT.md
           (applied actions · conflicts[board/gh/watermark] · unlinked both sides · orphans)
```

`board-reconcile.sh` gains one line: if `SYNC-REPORT.md` carries unresolved conflicts, surface "board-sync: N conflicts pending" so the orchestrator sees it on wake. The report file is the durable artifact for unattended runs; a per-issue GitHub comment on conflict is a deferred option (Out of scope).

## 4. Scope & phasing — built in verifiable layers

The chosen scope is **state + labels + edges**. Because labels and edges each extend the core (new fields, a GitHub-body edge protocol), v1 ships as three layers, each independently testable and landable.

### Layer 1 — state + close-reason (the core)

| board state | GitHub | direction notes |
|---|---|---|
| `done` | `closed` / `stateReason=completed` | board→GH: close as completed. GH→board: only-GH close/completed → `done` **when the board ticket is done-reachable (`in-progress`/`in-review`)**; otherwise reported — the board never started it, which is itself a surprise for the human. |
| `wontfix` | `closed` / `stateReason=not_planned` | board→GH: close as not_planned. GH→board: only-GH close/not_planned → `wontfix` (with a script-required note). |
| `ready-for-agent`, `in-progress`, `blocked`, `needs-info`, `in-review`, `deferred` | `open` | GH `open` ↔ **any** board "open" state. The fine state is board-only and is **never inferred** from GitHub. board→GH: ensure the issue is open. |

`board→GH` is fully deterministic. `GH→board` is deterministic for `close→wontfix` (via `stateReason=not_planned`, legal from any non-terminal state) and for `close→done` **only when the board ticket is `in-progress`/`in-review`** (the board state machine forbids `done` from other states — a GitHub-completed issue whose board ticket never started is reported, not forced). A **GitHub reopen** of an issue whose board state is `done`/`wontfix` is genuinely ambiguous (to *which* open state?) → **report, agent/human decides** — it is never auto-applied.

### Layer 2 — labels

- **Free labels** (everything except managed ones) mirror **bidirectionally** as a set into node `labels[]`; the watermark tracks the last-synced set, so per-label add/remove propagates each way. A both-changed-the-same-label disagreement is a conflict → report.
- **Managed labels** are one-way `board→GH`, board-authoritative, and excluded from the free mirror (so they never round-trip into `labels[]`): `epic` (derived — the node has children); `category` (the node's `bug`/`enhancement` field maps to the matching GitHub label — it is already a first-class node field, not free text); and an optional `state:<board-state>` projection so a human browsing GitHub can see the fine state GitHub itself can't hold. The `state:*` projection is included as opt-in (default on); it is pure board→GH and never pulled back.

### Layer 3 — edges

- `blocked_by` ↔ a machine-parseable block in the GitHub issue body: `<!-- board:blocked_by #68,#70 -->`, issue numbers resolved through the `gh` link field. `board→GH` writes/updates the block; `GH→board` parses it and re-cuts edges via `board-edge.sh`. The board is the natural authority (edges are cut by the orchestrator), but a body edit that changes the block pulls back; disagreement → conflict → report.
- `parent` / `spawned_by` / `relates_to` are **not** synced in v1 (`parent`'s epic-membership is visible via the `epic` label; native GitHub sub-issues are beta and non-portable). Only `blocked_by` crosses.

## 5. Conflict & unattended policy

- **Conflict** (both sides moved a facet away from the watermark, to disagreeing values) → board-sync mutates **neither** side; it records `{board, gh, watermark}` in the report. This preserves "the orchestrator is the board's sole writer" for contested writes and never silently discards a human's or a daemon's intent.
- **Unattended (cron)** → **conservative**: auto-apply only facet changes on already-linked tickets. **Creating a counterpart** (a GitHub issue for a board-only ticket, or a board ticket for an issue-only) and **conflicts** are report-only — issue creation is outward-facing and ticket birth needs a pre-spec, both human-judged. Under human invocation the agent may walk those interactively.

## 6. Trigger & runtime

- **Invocation** — a `/board-sync` slash command, or the orchestrator dispatching the `board-sync` subagent (model: `sonnet` — cheap judgment over a deterministic plan).
- **Cron** — `CronCreate` schedules a prompt that invokes the agent. Proposed cadence: daily, plus on-demand. (Cadence value is tunable and not load-bearing.)
- **Runtime** — runs from the **main checkout** (board scripts refuse worktrees) with `gh` already authenticated in the environment. Built against the **plugin source** (`BOARD.*`, `board-edge.sh`, etc.); a consumer repo pinned to an older installed version (e.g. ida-solution on 6.1.1) gets board-sync on the next plugin upgrade — a release/version-bump concern, not a design one.

## 7. Testing

- `board-gh-plan.sh` is a pure function of (`map.json`, `gh` JSON, watermark) → hermetic unit tests under `tests/issue-tracker/` with fixtures asserting the emitted plan: completion drift each direction; GH-reopen → conflict/report; label add & remove each direction; label conflict → report; edge add via body block → edge re-cut; `--backfill` title parse; unlinked on each side; no-op when already agreed.
- `board-gh-apply.sh --dry-run` prints the exact `board-*.sh`/`gh` calls → asserted hermetically (no network). The live `gh` path is a documented manual smoke.

## Acceptance (observable behavior)

- A linked ticket the board flipped to `done` whose issue is still open: one run closes the issue as `completed`, writes the matching watermark, and a second run is a no-op.
- An issue closed as `not_planned` on GitHub while the board still shows it active (only GitHub moved): a run flips the board to `wontfix` with a note, via `board-transition.sh`.
- Both sides moved the same ticket to disagreeing states since the last sync: the run changes neither side and records the conflict (`board`/`gh`/`watermark`) in `SYNC-REPORT.md`; the ticket's watermark is left stale so it re-flags next run.
- A ticket titled `… (GH#27)` with no `gh` field: `board-link.sh --backfill` sets `gh:27`; subsequent runs never read the title.
- An unattended cron run: no GitHub issue and no board ticket is created; unlinked items on both sides appear in the report only.

## Out of scope (deferred)

- Auto-creating counterparts unattended (creation stays a human-invoked, judged action).
- Title/body prose sync — only the machine `blocked_by` block inside the body is touched.
- GitHub **native** issue dependencies / sub-issues (beta, non-portable); the body-comment block is the portable representation — revisit if it reaches GA.
- `parent` / `spawned_by` / `relates_to` edge sync (v1 crosses `blocked_by` only).
- Per-issue GitHub **comment** on conflict (the `SYNC-REPORT.md` file is the v1 sink).
- GitLab or any non-GitHub forge (`gh`/GitHub only).
- Per-facet timestamps in `map.json` (the watermark substitutes for change detection).

## Decision Log

- **2026-07-05 — Mechanics: deterministic toolkit + agent judgment (hybrid).** The agent drives scripts; it never hand-edits `map.json`.
  - *Rejected — freehand agent* (LLM runs ad-hoc shell to edit `map.json`/`gh` directly): bypasses the script-enforced invariants (transition legality, mandatory notes, epic/unblock sweeps, edge cycle checks, `BOARD.*` re-render), risks JSON corruption, is non-auditable/non-reproducible, and is unsafe on an unattended cron with write access. The substrate's own rule is "use the scripts, don't hand-edit."
  - *Rejected — pure script, no agent*: cannot judge ambiguous close-reason mapping (GH reopen), conflicts, or whether an unlinked issue belongs on the board.
- **2026-07-05 — Direction: bidirectional reconcile against a last-sync watermark.**
  - *Rejected — pure one-way*: neither direction suffices alone — completions need board→GH (close the issue), staleness needs GH→board (a human closed it on GitHub). The watermark is the only available change-detector because `map.json` has no per-field timestamps.
- **2026-07-05 — Conflict policy: report-only, no auto-resolve.**
  - *Rejected — board-wins*: silently discards a human's GitHub action. *Rejected — GH-wins*: silently discards a daemon/orchestrator board decision. Reporting keeps the sole-writer invariant for contested writes; conflicts are rare, so the human cost is low.
- **2026-07-05 — Linkage: structured `gh` node field + one-time title backfill.**
  - *Rejected — parse `(GH#NN)` from title every run*: fragile to title edits, blanks, multiple references. *Rejected — separate mapping file*: dual-maintenance; the link belongs beside `pr`/`branch` on the node.
- **2026-07-05 — Unattended cron: conservative.** Auto-apply facet changes on linked tickets only; counterpart creation and conflicts are report-only.
  - *Rejected — aggressive* (auto-create counterparts unattended): outward-facing issue creation and pre-spec authoring without a human. *Rejected — cron report-only* (never mutate on cron): fails the core goal of preventing drift automatically.
- **2026-07-05 — Scope: state + labels + edges, shipped in three verifiable layers.**
  - *Rejected — core-only (state)*: the human wants labels and edges kept in lockstep. Layering (state → labels → edges) contains the added complexity so each lands and is tested independently rather than as one large change.
- **2026-07-05 — Packaging: a registered `board-sync` subagent + toolkit in `skills/issue-tracker/scripts/`** (approach A), not a skill-only or a proposal-daemon design — cron needs an autonomous agent, and the mutation-bearing logic belongs in deterministic board scripts next to their peers.

## Surprises & Discoveries

- The issue-tracker's **sole-writer + script-enforced-legality** invariant is *why* freehand is out — not a style preference. Hand-editing `map.json` bypasses the epic/unblock sweeps and transition legality and can silently break eligibility or corrupt the file.
- There is **no structured ticket↔issue link** today (title text only) and **no per-field timestamps** on nodes. Both gaps directly forced concrete choices here: the `gh` field, and the `.sync-state.json` watermark as the only way to attribute a change to a side.
- GitHub cannot **portably** represent the board's fine states or `blocked_by` edges (native dependencies are beta). Hence: fine state stays board-only, an optional `state:*` label projection makes it visible one-way, and edges ride in a machine-parseable body comment.
- The substrate spec (2026-07-03) had already **explicitly deferred** "GitHub/GitLab sync or export" — board-sync is the planned successor to that deferral, not a new direction.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-05: Initial design from a brainstorming session. Six clarifying questions locked the architecture (mechanics, sync direction, conflict policy, linkage, unattended aggressiveness, scope) — all captured in the Decision Log with their rejected alternatives. Open sub-choices resolved by the author within the approved design: `state:*` label projection included opt-in (board→GH one-way); report sink is `SYNC-REPORT.md` surfaced by `board-reconcile.sh`.
- 2026-07-05: Two refinements surfaced while writing the implementation plan (`docs/doperpowers/plans/2026-07-05-board-sync.md`). (1) Dropped the `version` 1→2 bump — the new `gh`/`labels` fields are additive and optional, so readers using `.get()` need no migration and old boards load unchanged; version stays `1`. (2) `GH→board` `done` is auto-applied only when the board ticket is done-reachable (`in-progress`/`in-review`); the board state machine forbids `done` from other states, so a GitHub-completed issue whose ticket never started is reported rather than force-transitioned. `§1 Schema` and `§4 Layer 1` updated accordingly.
