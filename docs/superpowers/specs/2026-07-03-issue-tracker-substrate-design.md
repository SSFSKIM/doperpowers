# Issue-Tracker Substrate — Design

**Goal:** A local, repo-portable issue board for doperpowers: tickets are purpose-units born as pre-specs from `issue-register`, driven end-to-end (brainstorm → spec → plan → build → PR) by background daemons, and tracked as nodes in a JSON graph that the central main session — the orchestrator — owns exclusively.

**Actors.** Two roles, one substrate:

- **Orchestrator** = the central main Claude session (a *role*, not a standing process — whichever main session is currently active). Talks to the human, runs `issue-register`, dispatches daemons, judges their proposals, and is the **sole writer** of the board.
- **Worker** = a durable background daemon (per `orchestrating-daemons`), bound to one ticket, driving it through the full development pipeline in an isolated worktree. Workers never write the board; they *propose* transitions.

## 1. Directory layout

Data lives in the **consumer repo**, namespaced under the plugin:

```
<repo>/doperpowers/issue-tracker/
  map.json          # graph + states — orchestrator-only, canonical in MAIN checkout
  log.jsonl         # append-only audit log — orchestrator-only
  tickets/
    T7-<slug>.md    # ticket content: pre-spec + decision log
```

Code ships **with the plugin**:

```
skills/issue-tracker/
  SKILL.md          # orchestrator manual: vocabulary, toolkit, dispatch/judge/reconcile loop,
                    # plus an embeddable "Worker Protocol" block for spawn prompts
  scripts/
    _lib.sh  board-register.sh  board-transition.sh  board-list.sh
    board-show.sh  board-bind.sh  board-reconcile.sh
```

**Bootstrapping is lazy:** no setup skill. The first `board-register.sh` in a repo creates `doperpowers/issue-tracker/` + an empty `map.json`. There is no tracker choice to configure — the board is always this local one.

**Canonical-copy rule:** only the orchestrator writes `map.json`/`log.jsonl`/`tickets/*.md`, and only in the repo's **main checkout**. Worktree copies are stale snapshots nobody edits — so branches never modify the board and merge conflicts are structurally impossible. Every script refuses to run from a worktree.

## 2. map.json schema

```json
{
  "version": 1,
  "next_id": 8,
  "tickets": {
    "T7": {
      "title": "worktree map viewer",
      "md": "tickets/T7-worktree-map.md",
      "state": "ready-for-agent",
      "category": "enhancement",
      "note": null,
      "parent": "T3",
      "blocked_by": ["T5"],
      "spawned_by": null,
      "relates_to": [],
      "branch": null,
      "pr": null,
      "created": "2026-07-03",
      "updated": "2026-07-03"
    }
  }
}
```

- **Edges:** `parent` (epic decomposition — a node with children *is* an epic; no type field), `blocked_by` (serialization), `spawned_by` (follow-up provenance), `relates_to` (optional).
- **`note`:** mandatory for `blocked` / `needs-info` / `wontfix` (script-enforced); optional elsewhere.
- **Lifetime rule — what lives here vs. the daemon registry:** the map holds only *project-lifetime* data. `branch`/`pr` are git-durable → map. Session UUID and worktree path are *machine-lifetime* → they live in the daemon registry only: `board-bind.sh` writes a `ticket: T7` key into the daemon's meta JSON (`~/.claude/orchestrating-daemons/<uuid>.json`). Ticket→daemon lookup scans the registry. Nothing is stored twice.
- **IDs:** `T<n>` from `next_id`, never reused.

## 3. State machine

Eight states. `category` (`bug` | `enhancement`) is an orthogonal tag.

| state | meaning | note |
|---|---|---|
| `ready-for-agent` | pre-spec complete, no non-ticket blockage; dispatchable | — |
| `in-progress` | a daemon is driving it (an epic stays here while children run) | optional |
| `blocked` | **non-ticket** blockage only: credentials/auth/human hand. Ticket dependencies are *derived* from `blocked_by` edges, never stored as state | **required** (on what) |
| `needs-info` | waiting on knowledge: research or a genuine human taste/product decision | **required** (what info/decision) |
| `in-review` | PR open — covers review, review-fix rounds, conflict resolution, merge queue | PR link |
| `done` | **landed** (merge verified). Follow-ups are edges, not a state | optional |
| `wontfix` | rejected | **required** (why) |
| `deferred` | tracked, not now; human decides when | optional |

**Discriminant** (goes verbatim into worker prompts): `blocked` = waiting on an *action/precondition*; `needs-info` = waiting on *knowledge/decision*.

**Transitions & invariants:**

```
birth (issue-register) → ready-for-agent | needs-info | blocked | deferred
dispatch gate: state == ready-for-agent  AND  every blocked_by ticket is done
in-progress ↔ needs-info | blocked        (worker escalates via proposal block)
in-progress → in-review                    (PR opened; branch/pr recorded)
in-review  → done                          (only after the merge is verified landed — merge-gated)
any → wontfix | deferred                   (human/orchestrator judgment)
done sweep (automatic in board-transition): re-evaluate every ticket whose blocked_by
  contains this one; check the parent epic for all-children-done → parent done
```

**Epic rule:** a node with children is never dispatched — its work *is* its children.
Its state is maintained by `board-transition`'s sweep: first child moves to
`in-progress` → parent set `in-progress`; all children `done` → parent set `done`.

## 4. Script toolkit

Pattern-matched to the `orchestrating-daemons` toolkit: bash + inline python3 stdlib, atomic writes (tmp + `os.replace`), no dependencies. **Scripts enforce invariants; the LLM judges semantics.**

| script | does |
|---|---|
| `board-register.sh <title> <category> <md> [parent] [blocked-by…]` | allocate ID, add node, initial state; lazy-creates the data dir |
| `board-transition.sh <id> <state> [note]` | validate transition legality, enforce mandatory notes, run the done-sweep, append to `log.jsonl` |
| `board-list.sh [state]` | board view; computes **eligibility** (ready-for-agent + all blockers done + not an epic) |
| `board-show.sh <id>` | node + ticket md path + bound daemon (registry scan) |
| `board-bind.sh <uuid> <id>` | write `ticket` key into daemon meta (additive JSON merge; zero edits to the daemon toolkit) |
| `board-reconcile.sh` | **read-only reporter**: scan daemon replies for proposal blocks + git/PR reality; print proposed transitions and anomalies (e.g. in-progress ticket whose daemon is gone). Applying is the orchestrator's judge step, via `board-transition.sh` |

Shared guard in `_lib.sh`: resolve repo root, refuse worktrees, locate `doperpowers/issue-tracker/`.

## 5. issue-register changes

The final steps stop producing a standalone register artifact and emit into the board instead:

- Step 6 (was "write the register") → **register each work-item**: `board-register.sh` per item, then write `doperpowers/issue-tracker/tickets/T<n>-<slug>.md` — a **self-contained pre-spec** carrying every decision from the grilling (template in §6).
- Status mapping: complete & unblocked pre-spec → `ready-for-agent`; needs-more-grilling → `needs-info`; parked → `deferred`; dependencies → `blocked_by` edges; cluster hierarchy → `parent` edges.
- Step 7 handoff → pass **board ticket IDs** (the register artifact *is* the board now).

`issue-register` remains a main-session, human-dialogue skill; it is the board's birth channel.

## 6. Ticket markdown

```markdown
---
id: T7
title: worktree map viewer
category: enhancement
---
## Problem & intent      ← what and why, user's perspective
## Constraints           ← non-negotiables
## Success criteria      ← outcome, not implementation
## Open questions        ← unresolved after grilling
## Decision log          ← every decision from the grilling, dated
```

- **No `state` in frontmatter** — single source of truth is `map.json`.
- **Written only by the orchestrator**: at registration, and a terminal outcome summary appended at `done`/`wontfix`. Workers *read* it; their specs/plans go to their own worktree's `docs/superpowers/` as usual.

## 7. Dispatch flow (orchestrator procedure, in SKILL.md)

```
board-list → eligible tickets
→ daemon-spawn.sh "T7-<slug>" "<self-contained prompt: ticket md content + Worker Protocol block>" <repo> <worktree-name>
→ board-bind.sh <uuid> T7
→ board-transition.sh T7 in-progress
… daemon ends a turn; reply ends with a proposal block …
→ orchestrator judges (answer / queue for human / apply) → board-transition.sh
… orchestrator was away? → board-reconcile.sh on wake catches up
```

**Worker Protocol block** (embedded in every spawn prompt; maintained in SKILL.md — no separate worker skill for now):

- You own ticket T\<n\> end-to-end: brainstorm → spec → plan → build → PR, in your worktree.
- The board is **read-only** for you. To change state, end your turn with a proposal block:
  `{"ticket":"T7","from":"in-progress","to":"in-review","reason":"…","evidence":"PR #12"}`
- Escalation discriminant: waiting on an *action/precondition* → propose `blocked`; waiting on *knowledge/decision* → propose `needs-info`. State the question crisply and END YOUR TURN — never guess above your scope.

## 8. Edge cases

- **Daemon died / timed out:** `board-reconcile.sh` flags in-progress tickets with no live bound daemon → orchestrator respawns (new UUID, same ticket, re-bind).
- **map.json corrupted:** restore from git history (a side benefit of committing it).
- **Two concurrent main sessions:** rare; documented as unsupported rather than locked (the worktree guard already blocks the common accident). No advisory locking in v1.
- **Dangling refs:** `board-list.sh` warns on ticket md paths that don't exist.

## 9. Testing

Hermetic toolkit test under `tests/` (following the orchestrating-daemons suite): register → transition → done-sweep unblocks dependents → epic auto-close; illegal transition refused; mandatory note enforced; worktree guard refuses; atomic write survives interruption (tmp file left behind is ignored).

## Out of scope (deferred)

- A dedicated **worker-side skill** — the spawn-prompt Worker Protocol block is the delivery channel for v1; promote to a skill only if real usage shows it insufficient.
- GitHub/GitLab sync or export.
- Any dashboard/visualization of the map.
- Advisory locking for concurrent main sessions.
- Auto-dispatch daemons on registration (dispatch stays an explicit orchestrator/human action).
