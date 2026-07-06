# issue-tracker v7 — GitHub Issues as the Single Source of Truth — Design

**Goal:** Eliminate board drift *structurally* by reducing the number of state stores to one. The local `board.json` (and everything that existed to keep it honest — board-sync, `.sync-state.json`, watermark reconciliation, the worktree guard) is retired; **GitHub Issues becomes the board**. The toolkit's script names, CLI contracts, state machine, dispatch loop, and worker proposal protocol survive unchanged — only the storage backend moves. Supersedes the sync layer of `2026-07-05-board-sync-design.md`.

## Problem

v6's board is three copies of the same state: the local-branch `board.json`, the origin `board.json`, and the GitHub issues. Two of the three are **versioned in git**, so every branch is an automatic board fork. Observed failure classes, all structural rather than disciplinary:

1. **Two-way fork** — `main` and an integration branch evolve `board.json` independently; the same T-ID comes to denote *different tickets* (ida-solution T51, 2026-07). No 3-way merge is safe; canonical state had to be re-derived from GitHub by hand.
2. **Reconciliation is unbounded work** — board-sync Layer 1 shipped, but Layers 2–3, cron arming, close-reason mapping, and conflict adjudication were all still open. Every fix added sync machinery; none removed the cause.
3. **The guard fights the workflow** — the single-writer/main-checkout rule (needed only because `board.json` is a git file) collided with worker-owned tickets in worktrees, spawning 6.3.4's opt-out carve-outs.
4. **The de-facto SSOT was already GitHub** — consumer automation (ida-solution `issue-status-labels.yml`) was writing `status:*` labels on assign/PR/merge before the local board heard about any of it. The local board was the stale mirror chasing GitHub, not the other way round.

A store that exists in N places needs N−1 synchronizers. The only zero-sync design is N=1, and GitHub is the copy we cannot delete (PR closing refs, review, CI automation live there).

## Why GitHub can hold the schema now (verified 2026-07-06)

The historical objection — "GH issues are free text + labels, `board.json` has a typed graph" — is obsolete. Probed live against `IDA-solution/ida-solution` (no preview gates, org on the free plan):

- **Reads** on `Issue`: `parent`, `subIssues`, `blockedBy`, `blocking`, `issueDependenciesSummary`, `linkedBranches`, `issueType`.
- **Mutations**: `addSubIssue`, `removeSubIssue`, `reprioritizeSubIssue`, `addBlockedBy`, `removeBlockedBy`.

Field-by-field, `board.json` → GitHub:

| board.json | GitHub native | note |
|---|---|---|
| ticket id (`T51`) | issue number | the `gh` link field — and the fork bug class — vanish |
| `title` | issue title | |
| `md` (pre-spec file) | issue body | file management disappears |
| `state` (8-state machine) | open + one `status:<state>` label; terminal via close reason | see §2 |
| `category` | `bug` / `enhancement` labels | already GH-native |
| `parent` | **sub-issue** (`addSubIssue`) | typed, verified |
| `blocked_by` | **dependency** (`addBlockedBy`) | typed, verified — the DAG edge |
| `branch` / `pr` / `spawned_by` / `relates_to` | `board:meta` body block (§3) + native timeline links | the only convention-typed remainder |
| `note` | `[board]`-prefixed issue comment | audit trail upgrade: full timeline |
| `created` / `updated` | issue timestamps | |
| `labels[]` | labels | the `board-meta.sh` writer becomes redundant |
| `log.jsonl` | issue timeline events | native, per-actor, undeletable |
| `next_id` | — | gone |

## Design overview

**Same toolkit, new backend.** Every `board-*.sh` keeps its name and argument contract (issue-register, orchestrating-daemons, and consumer CLAUDE.md files reference them by shape); ticket IDs become plain issue numbers. All scripts talk to GitHub through `gh` (REST via `gh issue`, graph edges via `gh api graphql`). No third-party dependency is added — `gh` was already required by board-sync and the consumer workflow.

Approaches weighed:

- **A — GitHub Issues as SSOT** (chosen). Zero new dependencies; typed graph primitives now native; the consumer's existing label automation becomes a free board writer; the sync problem is deleted rather than solved.
- **B — Linear as SSOT** (the agent-harness/Symphony precedent). Best-in-class board UX and API, but GitHub Issues cannot be abandoned (closing refs, review flow), so Linear↔GH bidirectional sync reappears — the same problem class we are removing, relocated. Also violates the fork's zero-dependency stance. agent-harness itself keeps the board behind a config adapter (`logical→Linear state-name map`), confirming the board vendor is swappable — and GH now has the three primitives Symphony actually needs (typed blocker edges, a state machine, a per-ticket thread).
- **C — self-hosted remote board (Supabase table / gist)**. Removes the git-fork problem but keeps two stores (it + GitHub), so reconciliation survives; adds infrastructure to maintain. Rejected.

## 1. Identity & repo resolution

- A ticket **is** a GitHub issue; scripts accept `42` or `#42`.
- Target repo: `$BOARD_REPO` (owner/name) if set, else `gh repo view --json nameWithOwner` of the cwd. All `gh` calls pass `-R "$REPO"` explicitly.
- **Fail-loud**: `gh` missing, unauthenticated, or offline → `die` with the exact remedy. No local fallback, no cache-as-truth.
- The worktree guard is deleted — no git file is written, so any checkout (including worker worktrees) may run any script. The 6.3.4 carve-out becomes moot.

## 2. State encoding

The v6 state machine is preserved verbatim (same states, same legality table, same mandatory notes). Encoding:

| state | GitHub encoding |
|---|---|
| `ready-for-agent`, `in-progress`, `blocked`, `needs-info`, `in-review`, `deferred` | **open** + exactly one `status:<state>` label |
| `done` | **closed**, reason `completed` |
| `wontfix` | **closed**, reason `not planned` |

- Reading: closed→reason decides; open→the single `status:*` label; open with zero or ≥2 status labels → **invalid** (transition dies with a FIX line; lint flags it).
- Transition = remove old label + add new (one `gh issue edit --remove-label --add-label` call), or close/reopen with reason. Status labels are stripped on close.
- `board-transition.sh` keeps: the legality matrix, mandatory notes (`blocked`/`needs-info`/`wontfix`), mandatory `--pr` for `in-review`, and both **epic sweeps** (first active child pulls the parent chain to `in-progress`; all-children-terminal-with-≥1-done closes the epic), now computed over `parent`/`subIssues`. Notes land as `[board] <state>: <note>` comments.
- Labels are lazily ensured: the first write in a repo creates any missing `status:*` labels with a fixed palette (idempotent).
- Bonus: ida-solution's `issue-status-labels.yml` (assign→`status:in-progress`, PR ready→`status:in-review`, merge→`status:done`) already speaks this exact vocabulary — GitHub-side automation becomes a legitimate board writer instead of a drift source. (Consumer follow-up: that workflow's merge step should close with reason `completed` rather than add `status:done`; harmless until then, lint will name it.)

## 3. The `board:meta` body block

The four convention-typed fields live in one HTML-comment block at the end of the issue body — invisible in the rendered issue (native UI already shows linked branches/PRs), machine-parseable in the one fetch that already returns the body:

```
<!-- board:meta
spawned-by: #12
relates-to: #3 #7
branch: feat/x
pr: https://github.com/o/r/pull/9
-->
```

Scripts read-modify-write the block, preserving all body text outside it; absent keys are simply omitted (N/A ⇒ not written). `board-relate.sh` edits `relates-to` (symmetric: both issues); `board-transition.sh --branch/--pr` writes `branch`/`pr` (the `--pr` comment’s URL mention also produces a native timeline cross-link for free).

## 4. Reads: one snapshot query

`_lib.sh` gains `_board_snapshot` — a single paginated GraphQL query fetching every issue's `number, title, state, stateReason, labels, assignees, parent, subIssues, blockedBy, body, updatedAt` into a tmp JSON. `board-list`, `board-map`, `board-show`, `board-reconcile`, and `board-lint` all consume it (one network round-trip per command, ~1 point per 100 issues against the 5 000/hr GraphQL budget).

- **ELIGIBLE** (dispatchable) = open, `status:ready-for-agent`, every `blockedBy` issue closed-`completed`. A blocker closed-`not planned` marks the dependent **STUCK** (human re-cuts the edge or wontfixes) — same semantics as v6.
- `board-map.sh` keeps both renders (the interactive layered-DAG `BOARD.html` and the `BOARD.md` table) with the data source swapped. Renders go to `doperpowers/issue-tracker/` which the script seeds with a `.gitignore` containing `*` — **render caches never commit again**. (The GitHub Issues UI itself is now the durable human view; a Projects v2 board can be layered on later without any schema work.)

## 5. Enforcement — three layers (schema without a schema engine)

GitHub will not reject a hand-made label soup at the API level, but neither did `board.json` reject a hand-edited JSON — the schema was always enforced by the *write path*, and that does not change:

1. **Scripts are the only write path.** Same rule as v6 ("don't hand-edit board.json" → "don't hand-write `status:*` labels / sub-issue / dependency edges with raw `gh`"). Register validates category/birth-state/note; transition validates legality/notes/PR; edge validates self-edges, cycles (walk `blockedBy` via the snapshot), ancestor-epic blockers.
2. **`board-lint.sh` (new)** — single-store invariant validation, replacing reconciliation entirely: every open issue carries exactly one `status:*` label; closed issues carry none; `blocked`/`needs-info` issues have a `[board]` note comment; every `in-progress` issue has an assignee; `board:meta` blocks parse. Prints `FAIL <#N> … FIX: <command>` lines, exit 1 on violations. Run on wake (board-reconcile calls it) and available for consumer cron.
3. **Consumer CLAUDE.md Hard Gate** — recommended text ships in SKILL.md: *"Board Write Hard Gate: issue creation and every state/edge change MUST go through the issue-tracker scripts — never raw `gh issue edit` for `status:*` labels or sub-issue/dependency edges. At registration, category + status label + parent + blocked-by are each either set or consciously N/A — silence is not N/A."*

## 6. Toolkit disposition

| script | v7 |
|---|---|
| `_lib.sh` | rewritten: repo resolution, `gh` preflight, state read/write helpers, label ensure, snapshot, meta-block parser. Worktree guard deleted |
| `board-register.sh` | `gh issue create` (pre-spec template body + category label + birth `status:*`) → `addSubIssue` / `addBlockedBy` edges → prints `<number> <url>`; the orchestrator then fleshes out the body (`gh issue edit -F`) |
| `board-transition.sh` | label swap / close-with-reason / reopen + note comment + meta block + epic sweeps + newly-eligible report |
| `board-edge.sh` | `addBlockedBy` / `removeBlockedBy` / `addSubIssue` / `removeSubIssue` with the v6 validation set |
| `board-relate.sh` | symmetric `relates-to` meta-block edit |
| `board-list.sh` / `board-show.sh` / `board-map.sh` | snapshot-driven; same outputs (ELIGIBLE tag, node detail, HTML/MD renders) |
| `board-reconcile.sh` | daemon-proposal catch-up (registry vs snapshot) + runs `board-lint.sh` |
| `board-bind.sh` | unchanged (daemon registry lives in `$DAEMON_HOME`, not the board) |
| `board-lint.sh` | **new** (§5.2) |
| `board-migrate-gh.sh` | **new, one-shot** (§7) |
| `board-link.sh`, `board-meta.sh`, `board-gh-plan.sh`, `board-gh-apply.sh` | **deleted** (linkage is identity; labels are native; there is nothing left to reconcile) |
| `agents/board-sync.md`, `commands/board-sync.md`, `.sync-state.json` | **deleted** |

Worker protocol, dispatch loop, and the deferral rule ("scope-outs become tickets in the same breath") survive with s/T-ID/issue number/. Workers stay read-only proposers — unchanged text, minus the worktree caveats.

## 7. Migration (`board-migrate-gh.sh`, one-shot per consumer repo)

Reads the legacy `board.json` and pushes everything GitHub does not already know:

1. Ensure `status:*` labels exist.
2. Per ticket **with** a `gh` link: set the status label (open) or close with the mapped reason (skip if already closed right); `addSubIssue` for `parent`, `addBlockedBy` for `blocked_by` (T-ID→number via the board's own `gh` fields); write the `board:meta` block from `spawned_by`/`relates_to`/`branch`/`pr`; if the ticket md file has body content beyond the title, append it to the issue body under `## Board pre-spec (migrated)`.
3. Per ticket **without** a `gh` link: create the issue via the new register path.
4. Print a summary; the operator then `git rm -r doperpowers/issue-tracker/` (history preserves the legacy board) and updates the consumer CLAUDE.md.

Dry-run by default; `--apply` mutates. ida-solution: 63 tickets, 63 already linked → step 3 is empty there.

## 8. Trade-offs accepted

- **Offline**: board ops need the network (~300–500 ms per `gh` call). Accepted; the board's consumers are online agents.
- **Concurrency**: a label swap is two label ops, not a transaction; simultaneous transitions of the *same* issue can race. The single-owner-per-ticket rule already makes this rare; lint detects the residue (double/zero status label). Cross-ticket concurrency — the case that used to corrupt `board.json` merges — is now GitHub's problem, serialized per-issue at the API.
- **Rate limits**: 5 000 GraphQL points/hr; a full snapshot of a 1 000-issue repo costs ~10. Not a constraint.
- **Board history in git** is lost; the issue timeline (per-actor, timestamped, undeletable) is strictly better audit.
- **Tests** can no longer poke a JSON file; the suite gets a PATH-shimmed mock `gh` that serves canned snapshot fixtures and records mutations (hermetic, no network — same seam board-gh-sync tests already use).

## Decision Log

- **GH Issues over Linear**: Linear relocates the sync problem instead of deleting it (GH issues are non-negotiable infrastructure); GH's 2025 primitives (sub-issues, dependencies) close the typed-graph gap that motivated Linear. Verified live before deciding.
- **GH Issues over self-hosted remote board**: any second store re-creates reconciliation; owning infra for tooling is negative leverage.
- **`status:*` labels over Projects v2 single-select field as the state store**: labels are readable/writable in one `gh issue` call and already automated in the flagship consumer; Projects v2 items need GraphQL project/item/field/option ID choreography per write. Projects v2 remains available as a pure *view* later.
- **Terminal states as close reason, not labels**: `closed/completed` and `closed/not planned` are GitHub's own vocabulary — native filters, native automation (`Closes #N`), no label to desync from the closed state.
- **`board:meta` HTML-comment block over issue comments or Projects fields** for `spawned-by`/`relates-to`/`branch`/`pr`: comes free with the body in every fetch; invisible to humans (native UI already renders branch/PR links); survives without extra API calls.
- **Keep the orchestrator/worker split and proposal protocol**: the failure being fixed was storage, not governance; workers writing GitHub directly would reopen the judgment layer question for no gain.

## Surprises & Discoveries

- GitHub's dependency/sub-issue GraphQL surface (`blockedBy`, `addBlockedBy`, `parent`, `addSubIssue`) is live on a free-plan org with no preview headers — probed against `IDA-solution/ida-solution` 2026-07-06 before this design was written.
- The flagship consumer's `issue-status-labels.yml` already speaks the exact `status:<state>` vocabulary this design standardizes — discovered convergence, not coordination.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-06: initial design (this document).
