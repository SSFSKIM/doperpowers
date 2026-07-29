# Human Control Plane — AI-Native Board Platform (2026-07-30)

> **Status:** design approved in-session (ideadump roadmapping, epic E3).
> This spec fixes the product boundary, the human surfaces, and the
> seams. It deliberately does NOT divide the platform into children —
> that decomposing run is gated on the cloud program's clean-slate
> research round (board-service internals are R2 material); this document
> is the parent input to that cut. Direction human-fixed 2026-07-30:
> **web UI with an embedded terminal, later compiled into a macOS app**
> ("이렇게한다"), on the Postgres-SSOT AI-native board.

## Purpose

A human cannot oversee thousands of swarm workers by attaching to
sessions one at a time, and the human's decision throughput on parked
work is the swarm's tightest bottleneck. After this platform exists, one
browser surface lets the human: watch the ticket topology live (tree +
kanban), open any ticket into its merged timeline (decisions + what the
bound session is actually doing), answer stacked decision batches from a
single queue — each answer waking the parked worker that filed it — and
drop into a live terminal on any running session. Later, the same
backends get a native macOS app with a real ghostty terminal.

## Product boundary

**A standalone product repo** (name: the human's call at creation).
Components: the **board service** (Postgres SSOT — the A0 Plan 1 board
service design is the seed), the **web UI**, and the **terminal/appserver
gateway**. doperpowers stays a skills plugin whose workers speak the
board API (zero-dependency identity preserved); cc-harness stays the
session runtime. **GitHub Issues and Linear are one-way outbound
mirrors** of the board ("just like Linear is a mirror of Postgres, GH
Issues can be the mirror") — edits on a mirror never mutate the SSOT.

## Surfaces

1. **Topology** — layered DAG with a kanban toggle, porting BOARD.html's
   proven interactions (pan/zoom, node detail, state filter, epic
   collapse) onto the board API.
2. **Ticket detail** — the E2 merged timeline (decision events
   interleaved with the derived session stream), links to the ticket's
   spec/plan artifacts (from the `plan:` meta field and body citations),
   and the bound session with live status.
3. **Unified needs-human queue** — ONE stack merging both park species:
   board parks (batch questions with recommended answers, rendered as
   preselected forms — the batch format is already structured enough to
   auto-render) and appserver-parked SDK decisions (permission requests,
   AskUserQuestion — cc-harness decisions-as-state). Answers relay per
   backend: board → answer event → sweep relay → worker resumes;
   appserver → `decision/respond` → immediate continue. The env-issue
   lane (E2) rides the same queue as a filter.
4. **Session terminal** — a web terminal client speaking through the
   control plane's authenticated proxy to the pod's ccx appserver WS.
   Auth and audit centralize at the gateway; no `pods/exec` RBAC grant to
   humans. Native ghostty arrives with the macOS app phase.

## Phasing

- **Phase web:** surfaces 1–4 in the browser, behind team auth (the
  Cloudflare Access pattern from the v8 hosted board is the precedent).
- **Phase native:** a macOS app hosting real ghostty against the same
  backends. Wrapper technology deferred to that phase.

## Acceptance (observable)

1. From the topology view, clicking a ticket shows its merged timeline
   and bound session, and one action opens a live terminal to that
   session in the browser tab.
2. The queue shows a board park and an SDK decision park side by side;
   answering the board park visibly resumes the bound worker (ticket
   returns to its pre-park state, session activity resumes); answering
   the SDK park unblocks its session immediately.
3. A board state change appears on the GitHub Issues mirror without any
   worker having written to GitHub; editing the mirror changes nothing
   on the board.
4. doperpowers workers drive their full protocol against the board API
   with no dependency on the platform repo beyond that API.

## Deferred / gated

- **Platform decomposition** (children: board service, UI, gateway,
  mirrors, app) — a decomposing run AFTER the cloud round fixes
  board-service internals (R2). This spec is the parent input; cutting
  now would violate the frontier discipline.
- Mirror field mapping; derived-stream retention; multi-human auth
  model; repo name.

## Decision Log

- Decision: Standalone product repo.
  Rationale: "new platforming" is the human's frame; the A0 board
  service was already designed as a standalone service; the plugin keeps
  its zero-dependency identity and consumes an API. Rejected:
  doperpowers monorepo (plugin identity, marketplace serving, and
  upstream-sync relations all complicate); absorption into cc-harness
  (the board is workflow state, the harness is session runtime —
  different concerns, and the board must not depend on the harness
  repo).
  Date/Author: 2026-07-30, human.
- Decision: Session entry = web terminal over the appserver WS through a
  control-plane proxy.
  Rationale: cc-harness M1 proved any client can drive a session
  (decisions-as-state, attach); a gateway proxy centralizes auth/audit;
  avoids granting humans `pods/exec` (broad lateral-movement RBAC).
  Rejected: local deep-link as the primary (abandons open-anywhere);
  raw `pods/exec` doors. Native ghostty deferred to the app phase
  (ghostty has no web embedding).
  Date/Author: 2026-07-30, human.
- Decision: Unified queue over both park backends.
  Rationale: two park species exist in the cloud runtime (board parks,
  appserver SDK decisions); a board-only queue either leaves SDK parks
  silent or invents new worker duties to promote them; two screens make
  the human patrol twice — against the queue's whole purpose.
  Rejected: board-only; separate screens.
  Date/Author: 2026-07-30, human.
- Decision: Vision-level spec now; division gated on the research round.
  Rationale: board-service internals (schema, claim path, mirrors) are
  R2 material under the 2026-07-30 clean-slate round; cutting children
  before that lands would produce stale cuts (decomposing's frontier
  rule).
  Date/Author: 2026-07-30, session, consistent with standing gates.

## Surprises & Discoveries

- Observation: the platform's hardest-looking parts already exist as
  shipped prior art — the DAG/kanban interactions (BOARD.html), the
  wake relay (`board-answer.sh` + sweep), and park/respond decision
  state (cc-harness appserver M1). The genuinely new construction
  reduces to the unified queue rendering, the WS terminal proxy, and
  the mirror writers.
  Evidence: issue-tracker v8 toolkit (`board-map.sh --serve`,
  `board-answer.sh`); cc-harness `docs/parity/coverage.md` (appserver
  M1, `ccx attach`).

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-30: v1, authored from the E3 grill of the ideadump roadmapping
  session (product boundary → session-entry seam → queue unification).
