# Surface Topology — Design

**Track:** controlled (spec here, implementation autonomous via execplan) ·
**Origin:** ida board audit 2026-08-10 (196 issues #958–#1252: 80%
worker-spawned, one SQL function fragmented across 7 open tickets whose
parallel rewrites silently reverted each other; duplicate integration
tickets #1074/#1092; invented `confident-ready` label) ·
**Interim guard:** 7.45.0 seam-search prompt policy (#52) — this design is
its mechanical successor.

## Purpose

The board's edge vocabulary (parent / blocked-by / spawned-by / relates)
records lineage and ordering but has no concept of a **code seam** — the
file, function, or contract a ticket touches. Ownership of a contested
surface (e.g. one SQL function's body) is therefore represented nowhere:
registration cannot see a collision, dispatch happily runs parallel
rewrites of one body, and the failure mode is silent (different files,
zero git conflicts, wrong final state). This design makes the surface a
first-class board concept: declared cheaply, derived mechanically,
serialized at dispatch, and policed by lint — so the class of incident
the audit found cannot recur silently.

Everything is **opt-in per consumer repo**: no `.doperpowers/surfaces.md`
→ no behavior change anywhere.

## The registry: `.doperpowers/surfaces.md`

Checked into the consumer repo (same discipline as `risk-surfaces.md`:
read from the TRUSTED base ref, never a PR head). One entry per **named
contested surface**:

```markdown
## recommend-for-student-rpc
- paths: sql/*recommend*.sql, lib/recommend*.ts
- identifiers: recommend_for_student
- born-of: ida#1258
- note: one function body; parallel CREATE OR REPLACE rewrites revert each other
```

- `paths` — glob patterns matched against declared hints and PR diffs.
- `identifiers` — substrings matched against ticket title/body at
  registration (the pre-PR signal).
- `born-of` — the consolidation ticket that created the entry.

Entries are born from incidents only: the cluster tripwire (a third open
ticket on one seam) raises a consolidation ticket (`ready-for-architect`),
and that ticket's design deliverable includes the surfaces.md entry,
landed by PR (human gate). No speculative taxonomy. Seed entries for ida:
`recommend-for-student-rpc`, `announce-hold-scrubber`,
`student-type-transition` (the audit's three proven clusters).

## Representation on the board

Two tiers, matching the board's existing storage split (states = labels,
edges = meta):

- **Named surface** → managed label `surface:<name>` — exact, quota-cheap
  collision queries (`gh issue list -l "surface:X" --state open`), visible
  in the UI. Label vocabulary is CLOSED: a `surface:*` label with no
  surfaces.md entry is a lint FAIL (the `confident-ready` lesson — no
  invented vocabulary).
- **Path-level surfaces** → `surfaces:` field in the script-owned
  `board:meta` block — free-form, populated from the PR diff (see below).

Declaration is a HINT; derivation is the truth:

1. **Register time** (`board-register.sh`, new optional `--surface`
   flag, repeatable): declared hints + title/body identifiers are matched
   against surfaces.md. On a match: apply `surface:<name>`, auto-relate
   the new ticket to every open ticket carrying the same label, and print
   that list to the registrar. This mechanizes the 7.45.0 seam-search
   duty — it fires even when the worker forgets.
2. **PR time** (sweep SURFACE pass): the PR diff's paths are matched
   against surfaces.md; labels are corrected/added and the actual touched
   paths are recorded in `board:meta` `surfaces:`. Omission or
   mis-declaration cannot dodge serialization — the diff is the backstop.

## Dispatch serialization

`implement-dispatch.sh --sweep`: a candidate ticket carrying
`surface:<name>` is dispatched only if no other ticket with the same
label is in-flight (`status:in-progress` or `status:in-review`).
Otherwise it is skipped with a logged reason
(`surface <name> occupied by #<n> — queued`) and retried next tick.
Registration is NEVER refused (knowledge is never lost — the invariant
governs parallel work, not parallel recording).

Exemptions: the architect lane (it is the resolver — a consolidation
ticket must dispatch onto an occupied surface) and the spike lane
(read-only exploration cannot rewrite a body).

Consequence: at most one PR per named surface is in flight, so the
mutual-revert scenario and the same-surface merge-ordering race are
mechanically impossible, not just discouraged.

## Sweep SURFACE pass

A light pass in `board-sweep.sh` (placement chosen over review-dispatch,
which only sees reviewed PRs, and over a GitHub Action, which inherits
runner/billing fragility):

- For each open PR linked to a ticket: diff paths vs surfaces.md →
  correct/add `surface:*` labels, write actual paths into `board:meta`,
  and add the retroactive relates edges label-mates are missing.
- Queue-depth watch: >= 3 open non-park implement tickets on one surface
  → post ONE consolidation-nudge comment on the oldest (deduped by a
  meta marker, same pattern as the epic-reconcile marker) proposing a
  `ready-for-architect` consolidation ticket.

## Lint

`board-lint.sh` additions:

- FAIL — `surface:*` label with no surfaces.md entry (closed vocabulary).
- WARN — declared surfaces contradicted by the PR diff (drift).
- Report — per-surface open-ticket queue depth.

## Migration

One-shot script: match the three seed patterns against OPEN ida tickets
(members already identified by the audit; tens of issues), apply labels.
No full-board backfill — everything else joins organically at next touch
(registration or PR). The live recommend-RPC cluster is thereby under
serialization from day one.

## Compatibility

- The A2 board-adapter work (doperpowers#44) is rebinding these same
  scripts to the Arkho board API. Surface logic must sit behind the same
  substrate seam A2 introduces: label queries and meta writes go through
  whatever the repo's bound substrate is; nothing in this design may
  hard-code gh beyond the existing pattern A2 is already abstracting.
  gh mode ships first.
- Repos without surfaces.md: `--surface` is accepted but a no-op with a
  notice; dispatch, sweep, and lint skip all surface logic.

## Acceptance (observable behavior)

1. Registering a ticket whose body names a seeded identifier
   auto-applies `surface:<name>`, auto-relates it to the open
   label-mates, and prints them — with no `--surface` flag passed.
2. With one `surface:X` ticket in-progress, a second `surface:X` ticket
   in `ready-for-implementer` is NOT dispatched by a sweep tick; the
   skip reason names the occupying ticket. It dispatches on the first
   tick after the first ticket leaves in-flight states.
3. An architect-lane ticket with `surface:X` dispatches regardless of
   occupation.
4. A PR whose diff touches a seeded path pattern gets its ticket
   labeled by the next sweep tick even when the registrar declared
   nothing.
5. A third open implement ticket on one surface triggers exactly one
   consolidation-nudge comment across repeated sweep ticks.
6. `board-lint.sh` FAILs an invented `surface:bogus` label and passes a
   registered one.
7. In a repo with no surfaces.md, all of the above is inert and the
   scripts' existing test suites still pass unchanged.
8. The one-shot migration labels the ida recommend-RPC cluster members;
   while any one of them is in-flight, the next sweep tick refuses to
   dispatch another.

## Delegated unknowns (empirical residue)

- Whether title/body identifier matching over-fires on incidental
  mentions (e.g. a ticket that merely cites the RPC in background) —
  measured after two weeks of live registrations; if noisy, tighten to
  declared-hint + PR-diff only.
- Whether one in-flight slot per surface is too tight for wide surfaces
  (a whole directory) — revisit if a queue starves; per-entry
  `max-in-flight` is the reserved extension, not built now.

## Decision Log

- **Surface ontology: two-tier (paths + curated named contracts)** over
  open vocabulary (rejected: vocabulary invention/divergence — the
  `confident-ready` failure; two names for one seam breaks collision
  detection) and over paths-only (rejected: cannot express "one function
  across many files" — the exact shape of the recommend-RPC incident).
- **Storage: hybrid — named surfaces as managed labels, paths in
  board:meta** over all-meta (rejected: collision query = fetch+parse
  every open issue) and all-labels (rejected: unbounded label
  proliferation for paths).
- **Curation: incident-born, registered by the consolidation ticket,
  landed by PR** over worker-immediate registration (rejected: registry
  bloat, vocabulary invention moved into a file) and human-only
  (rejected: needs-human queue is already saturated — 48 open at audit
  time).
- **Enforcement: dispatch-time serialization** over register-time
  refusal (rejected: recreates silent scope loss — contradicts "a
  follow-up not registered does not exist") and lint-only (rejected:
  post-hoc detection is exactly the failure mode being fixed).
- **Truth source: machine derivation (register-time matching + PR-diff
  backstop), declaration optional** over mandatory declaration
  (rejected: pre-work path prediction is guesswork; friction on
  docs/spike tickets) and diff-only (rejected: no signal exists at
  dispatch time, when serialization needs it most).
- **Migration: seed-3 one-shot, organic thereafter** over full backfill
  (rejected: hundreds of LLM classifications for a 3-entry registry) and
  none (rejected: the live recommend-RPC cluster is the motivating case
  and must be under serialization immediately).
- **PR-time matching placement: sweep SURFACE pass** over
  review-dispatch (rejected: covers only reviewed PRs) and GitHub Action
  (rejected: runner/billing fragility, #822 precedent). *(the one fork
  that emerged at design time; approved with the design)*
- Silent: `surface:` label prefix follows `status:`/`priority:`
  precedent; spike lane exempt from serialization; retroactive relates
  ride the sweep pass; `confident-ready` state-vocabulary cleanup is out
  of scope (separate small ticket); implementation lands as one
  doperpowers PR + one ida seed PR.

## Surprises & Discoveries

- The board had already self-diagnosed the duplicate (#1092's meta names
  the search-miss cause) — the gap was representation, not awareness.
- GitHub issue search hits body text, which makes identifier-based
  collision hints nearly free; but exact label queries are still the
  only precise primitive.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1 (2026-08-10): born landed from the grill (6 resolved forks + 1
  design-time fork).
