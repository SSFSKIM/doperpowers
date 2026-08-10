# Surface Topology — Design

**Track:** controlled (spec here, implementation autonomous via execplan) ·
**Origin:** ida board audit 2026-08-10 (196 issues #958–#1252: 80%
worker-spawned, one SQL function fragmented across 7 open tickets whose
parallel rewrites silently reverted each other; duplicate integration
tickets #1074/#1092; invented `confident-ready` label) ·
**Relation to #52:** the 7.45.0 seam-search prompt policy stays LIVE —
this design mechanizes collision handling for *registered* surfaces;
detection of *new* contested seams remains the prompt policy's job
(see Scope boundary).

## Purpose

The board's edge vocabulary (parent / blocked-by / spawned-by / relates)
records lineage and ordering but has no concept of a **code seam** — the
file, function, or contract a ticket touches. Ownership of a contested
surface (e.g. one SQL function's body) is therefore represented nowhere:
registration cannot see a collision, dispatch happily runs parallel
rewrites of one body, and the failure mode is silent (different files,
zero git conflicts, wrong final state). This design makes the surface a
first-class board concept: declared cheaply, derived mechanically,
serialized at dispatch, and policed by lint.

**Scope boundary (honest claim):** serialization is closed for
*registered* surfaces on the sweep-dispatch path (and, via the same
guard, triggered dispatch). It does NOT detect brand-new contested seams
— a fourth recommend-RPC-shaped incident on an unregistered seam is
caught by the #52 prompt policy (worker-side seam search and the
third-ticket tripwire), whose consolidation ticket then registers the
surface, bringing it under mechanical protection. Prompt policy finds;
machinery holds.

Everything is **opt-in per consumer repo**: no `.doperpowers/surfaces.md`
→ no behavior change anywhere.

## The registry: `.doperpowers/surfaces.md`

Checked into the consumer repo. **Authoritative ref:** all consumers
(register, dispatch, sweep, lint) read it from `origin/<default-branch>`
after the fetch they already perform — an entry takes effect only once
its PR lands on the default branch (the human gate), and a feature
branch's speculative entry has no effect. One entry per **named
contested surface**:

```markdown
## recommend-for-student-rpc
- paths: sql/*recommend*.sql, lib/recommend*
- identifiers: recommend_for_student
- born-of: ida#1258
- note: one function body; parallel CREATE OR REPLACE rewrites revert each other
```

- Entry name: kebab-case, ≤ 40 chars (it becomes the `surface:<name>`
  label; lint validates the file).
- `paths` — comma-separated fnmatch globs; `*` does not cross `/`,
  `**` does. Matched against PR diff paths (a rename counts both its
  old and new path).
- `identifiers` — case-sensitive whole-word matches (regex word
  boundary) against ticket title+body at match time.
- `born-of` — the consolidation ticket that created the entry.
- **Deletion:** an entry may be removed only after no open ticket
  carries its label (clear via `board-surface.sh --remove`); lint FAILs
  an orphaned label and its FIX line says exactly this.

Entries are born from incidents: a consolidation ticket
(`ready-for-architect`) — whether raised by a worker's tripwire (#52
policy) or by the sweep's queue-depth watch (below) — owns the redesign,
and its deliverable includes the surfaces.md entry, landed by PR. No
speculative taxonomy. Seed entries for ida: `recommend-for-student-rpc`,
`announce-hold-scrubber`, `student-type-transition` (the audit's three
proven clusters).

## Representation on the board

- **Named surface** → managed label `surface:<name>` — exact, quota-cheap
  collision queries, visible in the UI. Closed vocabulary: a `surface:*`
  label with no surfaces.md entry is a lint FAIL.
- **No path record in `board:meta`.** Path-level truth is the PR diff
  itself, recomputed on demand — v1's `surfaces:` meta field is dropped,
  deliberately: sweep-side body rewrites on tickets with live workers
  are the read-modify-write race the dispatcher already engineers
  around (parent-pin stamped pre-spawn for exactly this reason). Labels
  are atomic API adds and safe at any time; the only surface-driven
  body writes are relates edges, and those follow the deferral rule in
  Matching moment 3.
- **New verb `board-surface.sh <n> --add <name> | --remove <name>`** —
  the Hard-Gate-legal write path for surface labels. Register, sweep,
  and the migration script route through its shared lib; humans/agents
  use it directly to correct a false-positive match (`--remove` is the
  escape hatch the over-fire delegated-unknown expects). Lint FIX lines
  name it.
- A ticket may carry multiple surface labels (a consolidation ticket
  usually does). Semantics: it *occupies* every surface it carries;
  it *dispatches* only when ALL its surfaces are free; queue depth is
  counted per surface independently.

**Matching moments** (declaration is a hint; derivation is the truth):

1. **Register time** (`board-register.sh`, optional repeatable
   `--surface` hint): hints + title/body identifier match → label via
   the shared lib + auto-relate to open label-mates (idempotent:
   check-before-write; fan-out capped at the 8 most recent plus the
   open consolidation ticket if one exists) + print the label-mate list
   to the registrar.
2. **Transition time** (`board-transition.sh` entering any dispatchable
   lane state): re-run the identifier match against the CURRENT body.
   This catches the documented two-step flow (skeleton birth, body
   fleshed out via `gh issue edit` afterward) where register-time
   matching saw only a title.
3. **PR time** (sweep SURFACE pass): diff paths vs `paths` globs →
   **add-only** label correction (removal is never automatic — an
   early-WIP diff must not un-serialize a mid-flight ticket; stale
   over-declaration is surfaced as a lint WARN for a human to clear via
   `board-surface.sh --remove`). Relates edges for new label-mates are
   added only when neither ticket has a live bound worker
   (registry status `working`/`blocked`); otherwise deferred to a later
   tick — body writes never race a live worker.

## Dispatch serialization

The guard lives in `dispatch_one` — BOTH entry points (`--sweep` and
triggered `implement-dispatch.sh <n>`) inherit it; the hand-dispatched
hotfix on a contested surface is precisely the collision that matters.
Deliberate operator bypass: `SURFACE_OVERRIDE=1` env, logged loudly.

**Occupancy** of surface X is any open non-epic ticket carrying
`surface:X` that is:

- in `status:in-progress` or `status:in-review`, **or**
- bound in the daemon registry with status `working`/`blocked`
  (registry-first, like the slot count itself — board state lags a
  fresh spawn by minutes, and that window is exactly the double-dispatch
  race), **or**
- already claimed by an earlier dispatch in the same sweep tick
  (an in-memory claim set inside the sweep loop).

Lane rules:

- **Implement lane**: serialized — skip with logged reason
  (`surface <name> occupied by #<n> — queued`), retry next tick.
- **Architect lane**: never blocked (it is the resolver — a
  consolidation ticket must dispatch onto an occupied surface), but its
  in-flight tickets (`in-design` included) DO occupy against
  implementers: while the redesign runs, patch work waits.
- **Spike lane**: neither blocked nor occupying — read-only exploration
  cannot rewrite a body. (Occupancy queries fetch labels+state and
  exclude spike-category tickets and epic parents — pull-bookkeeping
  `in-progress` on an epic must not occupy forever.)

Registration is NEVER refused (knowledge is never lost — the invariant
governs parallel work, not parallel recording).

Consequence, scoped honestly: for labeled tickets, at most one
implement-lane worker per surface is in flight, so the mutual-revert
scenario and the same-surface merge race are closed on every
script-mediated path. Escapes that remain: a PR with no `Closes #N`
link (invisible to the board entirely — pre-existing), and the
architect's own consolidation PR coexisting with an occupant's PR
(intended: that PR is the fix).

## Sweep SURFACE pass

A light pass in `board-sweep.sh`, ordered **before DISPATCH** in the
tick (diff-derived labels must exist before dispatch decisions read
them; SURFACE-after-DISPATCH would always arrive one dispatch late).
Placement chosen over review-dispatch (only sees reviewed PRs) and a
GitHub Action (runner/billing fragility, #822).

- For each open PR linked to a ticket: diff vs `paths` → add-only
  labeling per Matching moment 3.
- **Queue-depth watch**: ≥ 3 open implement-lane (state-derived,
  non-park, non-epic) tickets on one surface AND no open consolidation
  ticket for it → the sweep REGISTERS the consolidation ticket itself
  (`board-register.sh --state ready-for-architect`, body naming every
  member — scripts are sanctioned board writers; a nudge comment would
  have no mechanical reader, since RELAY only serves needs-human parks).
  Dedupe is structural: the existence of an open architect-lane ticket
  carrying the surface label suppresses re-registration — no marker to
  drift, and closure of a member never double-fires (M2).

## Lint

`board-lint.sh` additions (each FAIL prints a FIX line naming
`board-surface.sh` or the file edit):

- FAIL — `surface:*` label with no surfaces.md entry (closed
  vocabulary; includes the entry-deletion-with-carriers case).
- FAIL — surfaces.md entry whose name is not kebab-case ≤ 40 chars.
- WARN — a labeled ticket whose merged/open PR diff never touched the
  surface's paths (stale over-declaration; human clears it).
- Report — per-surface open-ticket queue depth.

## Migration

One-shot script (routed through the `board-surface.sh` lib): match the
three seed patterns against OPEN ida tickets (members already identified
by the audit; tens of issues), apply labels. No full-board backfill —
everything else joins organically at the three matching moments. The
live recommend-RPC cluster is under serialization from day one.

## Compatibility

- **gh mode only, by design, for now.** In API/claim mode the server
  owns pick order; a client-side skip is head-of-line lane blocking
  (`_api_suppressed`: the suppressed ticket stalls everything behind
  it), so "skip and retry next tick" cannot be built client-side.
  Surface-aware pick order is therefore a **server-side requirement**
  recorded for A2/arkho (doperpowers#44) — the substrate seam does not
  absorb it, and this spec does not pretend it does.
- Repos without surfaces.md: `--surface` is accepted but a no-op with a
  notice; dispatch, sweep, and lint skip all surface logic.

## Acceptance (observable behavior)

1. Registering a ticket whose body names a seeded identifier
   auto-applies `surface:<name>`, auto-relates it to open label-mates,
   and prints them — no `--surface` flag passed.
2. A skeleton-born ticket whose body is fleshed out afterward gets its
   label at the next lane-entering transition (title-only birth,
   identifier only in the later body).
3. With one `surface:X` implement ticket in-flight (board state OR
   registry-bound worker) and cap headroom with no competing eligibles,
   a second `surface:X` implement ticket is not dispatched — sweep and
   triggered mode both — and the skip reason names the occupant; it
   dispatches on the first tick after occupancy clears. Two eligible
   `surface:X` tickets in ONE tick yield one dispatch (in-tick claim).
4. An architect-lane `surface:X` ticket dispatches onto an occupied
   surface; while it is in-design, an implement `surface:X` ticket
   waits. A spike ticket neither waits nor blocks.
5. A PR whose diff touches a seeded path pattern gets its ticket
   labeled by the next sweep tick even when the registrar declared
   nothing; an early-WIP diff that no longer matches never REMOVES a
   label.
6. A third open implement ticket on one surface causes the sweep to
   register exactly one consolidation ticket (`ready-for-architect`,
   body naming members); repeated ticks and member churn do not
   re-register while it stays open.
7. `board-lint.sh` FAILs an invented `surface:bogus` label with a FIX
   line naming `board-surface.sh`; passes a registered one.
8. `SURFACE_OVERRIDE=1` dispatches onto an occupied surface with a loud
   log line.
9. In a repo with no surfaces.md, all of the above is inert and the
   existing test suites pass unchanged.
10. The one-shot migration labels the ida recommend-RPC cluster
    members; while any one is in-flight, another is not dispatched.

## Delegated unknowns (empirical residue)

- Identifier over-fire rate on incidental mentions — measured after two
  weeks live; `board-surface.sh --remove` is the correction path; if
  noisy, tighten to declared-hint + PR-diff only.
- Whether one in-flight slot per surface starves wide surfaces —
  per-entry `max-in-flight` is the reserved extension, not built now.
- Mechanical detection of NEW contested seams (diff-overlap clustering
  across open PRs) — deliberately out of scope; #52 prompt policy owns
  it until incident volume justifies machinery.

## Decision Log

- **Surface ontology: two-tier (paths + curated named contracts)** over
  open vocabulary (rejected: vocabulary invention/divergence — the
  `confident-ready` failure) and over paths-only (rejected: cannot
  express "one function across many files" — the recommend-RPC shape).
- **Storage: named surfaces as managed labels; NO body-side path
  record** — v1 had paths in board:meta; dropped in v2 (review H2):
  sweep-side body RMW races live workers' own meta writes, and the diff
  is recomputable truth anyway. Labels are atomic adds.
- **Curation: incident-born, consolidation-ticket-registered, landed by
  PR** over worker-immediate (rejected: registry bloat) and human-only
  (rejected: needs-human queue saturation, 48 open at audit).
- **Enforcement: dispatch-time serialization in `dispatch_one` (both
  entry points, explicit `SURFACE_OVERRIDE=1` bypass)** over
  register-time refusal (rejected: silent scope loss) and lint-only
  (rejected: post-hoc = the failure mode). Occupancy is registry-first
  ∪ board-state ∪ in-tick claims — board-state-only reintroduces the
  double-dispatch window the dispatcher already documents (review C1).
- **Lane semantics (review H4): architect never blocked but occupies;
  spike neither; epics excluded** — the consolidation redesign is
  exactly when patches must wait; read-only exploration never rewrites;
  pull-bookkeeping must not occupy.
- **Truth source: machine derivation at three moments (register,
  lane-entering transition, PR diff), declaration optional** —
  transition-time re-match added in v2 (review H1: the documented
  two-step registration flow means register-time often sees only a
  title). Over mandatory declaration (guesswork, friction) and
  diff-only (no signal at dispatch time).
- **Label correction is add-only** (review H6): automatic removal would
  let an early-WIP diff un-serialize a mid-flight ticket; stale labels
  are lint WARNs cleared by a human via `board-surface.sh --remove`.
- **Consolidation is sweep-REGISTERED, not nudged** (review C3): a
  comment has no mechanical reader (RELAY serves needs-human parks
  only); registering `ready-for-architect` is Hard-Gate-legal for
  scripts, and structural dedupe (an open architect ticket carrying the
  label) replaces v1's per-ticket marker (review M2).
- **`board-surface.sh` verb** (review M4): the Hard Gate bans raw label
  surgery, so the system's own labels need a sanctioned write path —
  also the false-positive escape hatch.
- **Registry ref pinned to `origin/<default-branch>`** (review M1):
  entries take effect at human-gate landing, not from working trees.
- **Claim-mode honesty** (review H5): surface-aware pick order is a
  server-side A2 requirement, recorded, not papered over by "the
  substrate seam handles it".
- **Migration: seed-3 one-shot, organic thereafter** over full backfill
  (hundreds of classifications for a 3-entry registry) and none (the
  live cluster is the motivating case).
- **PR-time matching placement: sweep SURFACE pass, ordered before
  DISPATCH** (review M5) over review-dispatch (reviewed PRs only) and
  GitHub Action (#822 fragility).
- Silent: `surface:` prefix follows `status:`/`priority:` precedent;
  relates fan-out capped at 8 + consolidation ticket; `confident-ready`
  state-vocabulary cleanup out of scope (separate ticket);
  implementation = one doperpowers PR + one ida seed PR.

## Surprises & Discoveries

- The board had already self-diagnosed the duplicate (#1092's meta names
  the search-miss cause) — the gap was representation, not awareness.
- Independent review (fable subagent) found the v1 occupancy definition
  reintroduced the exact double-dispatch window `implement-dispatch.sh`'s
  own header warns about — the codebase knew; the spec hadn't read
  carefully enough. All 16 findings adopted in some form; none refuted.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1 (2026-08-10): born landed from the grill (6 resolved forks + 1
  design-time fork).
- v2 (2026-08-10): independent-review revision — occupancy hardened
  (C1), scope boundary vs #52 stated (C2), sweep-registered
  consolidation with structural dedupe (C3/M2), transition-time
  re-match (H1), board:meta path record dropped + body-write deferral
  (H2), guard moved to dispatch_one with override (H3), lane occupancy
  semantics (H4), claim-mode server-side requirement (H5), add-only
  labels (H6), registry ref pinning (M1), multi-label semantics (M3),
  `board-surface.sh` verb (M4), tick ordering + honest consequence
  claim (M5), testable acceptance preconditions (M6), matching contract
  (M7), deletion lifecycle / relate idempotence + cap / name
  constraints / lane-derived counting (L1–L4).
