# dp#51 — A1 consumption: binding the arkho#7 routes

**Purpose.** The arkho#7 architect pass (arkho PR #8, merged `a05b1ac`,
live on Render) gave the board service everything the A2 client deferred:
five human board-management routes, the run-actor leaf close (ruling R1),
design-first spike births (ruling R2), claim-response working bindings
(`pr`/`branch`), successor `parentPin`, a register `note` field, and a
read projection carrying `branch`/`blocked_by[]`/`relates[]`. This pass
teaches the doperpowers client side to consume all of it, so an api-bound
board reaches verb parity with gh mode everywhere the server now permits
— and retires every "no API-mode counterpart yet (A1 route gap)" refusal
that pointed at arkho#7.

Tracking issue: doperpowers#51 (consumption list in comment
`#issuecomment-5250126220`). Server contract: arkho
`board-service/API.md` at `a05b1ac`; design history in arkho
`docs/specs/2026-08-11-a1-human-routes-design.md` v1.8.

## Global constraints

- **Thin client.** API-mode verb branches assemble the request and report
  what came back. Legality, guards (cycles, ancestor-blocker,
  duplicate-edge, ticket-owned, write-if-changed) live server-side; the
  client never re-adjudicates them. The one licensed exception class is a
  gate the other binding enforces that the server does not (the
  board-transition `--plan` precedent); nothing in this pass needs one.
- **gh-mode byte-parity.** Every touched verb's gh-mode half stays
  behaviorally identical, except the one deliberate gh-mode change this
  spec names (board-body.sh's meta-preserving edit — a new verb, not an
  edit to an existing gh path).
- **No `gh` on api paths.** An api-bound repo must work on a machine with
  no GitHub CLI (established A2 invariant).
- **Errors surface verbatim.** `_board_api.py` prints
  `<code> — <message>`; no verb swallows or rewrites a server refusal.
- **Mock fidelity.** Unit-tier fixtures are shaped from the real
  service's observed output (success AND refusal envelopes), not from the
  caller's expectations. The error envelope is nested:
  `{"error": {"code": …, "message": …}}`.
- **Secrets.** Integration tier reaches the real service via
  `ARKHO_DIR` + the harness's scratch credentials. No board token, DSN,
  or `~/.arkho-board/` content is ever committed, echoed into fixtures,
  or logged.
- **Version bump at finish** via `scripts/bump-version.sh` (minor —
  feature surface), never hand-edited.

## Design

### 1. Edge verbs — `board-edge.sh`

Drop `_refuse_no_api_route` and add an api branch ahead of the gh python
block (the `board-transition.sh` pattern: same argv parsing, then
`if [ "$BOARD_BINDING" = api ]`). Route mapping, one operation per call
exactly as the CLI already enforces:

| CLI | Route | Payload |
|---|---|---|
| `--block N` | `POST /tickets/:id/edges` | `{"op":"add","blockedBy":N}` |
| `--unblock N` | `POST /tickets/:id/edges` | `{"op":"cut","blockedBy":N}` |
| `--parent N` | `POST /tickets/:id/parent` | `{"parent":N}` |
| `--orphan` | `POST /tickets/:id/parent` | `{"parent":null}` |

Principal `human` (the routes admit no other). Ticket refs accept
`#N`/`N` (the register `ref()` idiom). On success print the same move
lines the gh half prints (`#12: blocked_by += #41`,
`#12: parent = #41 (was none)`); the gh half's derived extras
("now eligible", epic pulls/recomposition) are server-side sweeps in api
mode and are not reprinted — the server's answer is `{"ok":true}` and the
line reports the op that committed. The header's guard paragraph gets an
api sentence: same refusal set, enforced by the server
(`self-edge`, `edge-cycle`, `ancestor-blocker`, `parent-cycle`,
`duplicate-edge`, `no-such-edge`, `not-found` naming missing ids).

### 2. `board-priority.sh`

Same shape: api branch posts `POST /tickets/:id/priority`
`{"priority":"P0"}` as `human`. Client still validates the grade against
`P0|P1|P2|P3` before the wire (arity/usage errors should not need a
socket), server owns the rest. Print `#12: → P0`, and append ` (noop)`
when the response carries `"noop": true` — the write-if-changed contract
is the visible difference from gh mode's label swap, and the flag is the
server saying "nothing was recorded".

### 3. `board-relate.sh`

Api branch: `POST /tickets/:id/relates` with
`{"op":"add"|"cut","ticket":B}` as `human`, sent to endpoint A (one
call — the server stores the edge normalized and both sides project it;
the gh half's two-issue write is gh-only bookkeeping). Print
`related: #a -- #b` / `cut: #a -- #b` as today. Self-relate is the
server's `self-edge` refusal (the existing `a == b` check is inside the
gh python block and stays there; the api branch does not duplicate it).

### 4. New verb — `board-body.sh`

`board-body.sh <number> --body-file F` (F may be `-` for stdin; an empty
file is a legal edit — clearing the statement of work).

- **api mode:** `POST /tickets/:id/body` `{"body": <file contents>}` as
  `human`. Print `#12: body rewritten` (` (noop)` on the flag). A
  `409 ticket-owned` refusal reaches the caller verbatim — the message
  names the owning run, and the enrichment channel for a bound park is
  the park answer, not the body; the header documents exactly that.
- **gh mode:** meta-preserving read-modify-write — but by **raw
  splice**, not `parse_meta`/`render_body`: extract the current body's
  literal `board:meta` suffix (the block `strip_meta` removes), append
  it to the new text **byte-for-byte**, write through
  `gh issue edit --body-file -`. The parse/render round-trip is wrong
  here: `parse_meta` reads a fixed key allowlist and `render_body`
  canonicalizes order and formatting, so an older client would silently
  erase keys a newer version introduced and reformat noncanonical
  blocks. A body-edit verb has no business interpreting the meta at
  all — it replaces the prose and carries the machine block through
  untouched — anchored on the RIGHTMOST `META_RE` match, because
  `re.search` is leftmost-first and the pattern's lazy middle backtracks
  across prose to the trailing `-->`, so a first-match offset would
  splice from a marker-like example quoted in the prose (measured:
  offset 29, inside the fake block, on the guard fixture). This is the
  missing safe counterpart to the documented "flesh out the body with
  `gh issue edit`" flow, which clobbers the `board:meta` block today. gh mode has no ownership guard (parity with
  existing gh-mode reality, where nothing stops a body edit; the api
  guard is a server invariant, not a client one).

`board-register.sh` pointers catch up: the header's
"then YOU flesh out the pre-spec body: `gh issue edit …`" line names
`board-body.sh` for api-bound repos, and the api-path comment claiming
"this client has no body-edit route (arkho#7)" is rewritten — the
skeleton-omission ruling it justifies still stands, but on its real
remaining ground (the skeleton's text must never become a park question
or a dispatched assignment; A1's body IS the claim-time assignment).

### 5. Register — real `note` field, spike note gone

`board-register.sh` api path:

- **Park-outcome births carry `payload["note"]`** instead of prepending
  the note to the body. The server judges `note-not-applicable` against
  the OUTCOME state (verified in `src/tickets.js`: the check runs on
  `birthState(...)`'s result), so all three client-known park outcomes
  ride it: explicit park births, the implicit env-issue inversion, and
  the client's own bodyless demotion to needs-info. The client already
  computes exactly this classification (the existing `PARK_BIRTHS` +
  `explicit` logic mirrors `birthState`). The body stays the statement
  of work; the question is stored whole as `park_note` server-side,
  verbatim.
- **A note on a non-park-outcome birth stays in the body head**, as the
  implicit path does today — the same prepend, now applied to explicit
  non-park births too (where the argument is silently dropped today).
  NOT a follow-up comment: registration commits before any second
  request, so a comment that fails loses the note behind a `duplicate`
  refusal on retry — and a *worker* registering a child cannot post it
  at all (`comment` scopes a run to its own ticket, and
  `_board_api.py`'s `token()` always speaks as the run when
  `BOARD_RUN_TOKEN` is in env, whatever principal a verb names). The
  prepend is atomic — one request — and principal-blind.
- **Client-side refusals stand unchanged**: the "park with no question"
  rule (`--note` required when neither note nor body exists for a park
  birth) mirrors a ruling the server deliberately does not enforce (its
  fallback chain note → body → title would make the ticket NAME the
  standing question); same for the env-issue intervention rule and the
  bodyless-dispatchable refusal/demotion.
- **The spike-birth divergence note dies.** R2 shipped: a spike born
  `ready-for-architect` is legal. The stderr-capture scaffolding around
  `A.register` exists only to attach that note to `illegal-birth`
  refusals — remove it and call `A.register(payload)` plainly. (A real
  `illegal-birth` still surfaces verbatim like any refusal.)

### 6. Scale review un-parks — `review-dispatch.sh` + reviewing-prs `SKILL.md`

The qagent claim response carries the working bindings: for an epic,
`pr` is the closure-package **event id** and `branch` the
**integration ref** (for a leaf: the PR URL and working branch). Consume
them at dispatch:

- `_claim_one_with_nonce`'s claim exchange additionally emits
  `C_PR=out.get("pr") or ""` and `C_BRANCH=out.get("branch") or ""`.
- **The dispatcher splits the variant; the render mode carries it.**
  The bootstrap template's `<!-- mode:X -->` blocks are exclusive — the
  renderer keeps only the selected block, so passing scale bindings
  under `P_REVIEW_MODE=api` renders them into nothing while the
  surviving api block orders PR resolution against an artifact that is
  not a PR. A **new `api-scale` mode block** joins the template: the
  scale framing (recomposition epic, closure package as entry artifact,
  no PR) composed with the api board substrate (board scripts + run
  credentials + `TICKET_BODY_FILE`), plus the two binding lines
  `CLOSURE_PACKAGE: {{CLOSURE_PACKAGE}}` /
  `INTEGRATION_REF: {{INTEGRATION_REF}}`. Split rule, on shape: `pr`
  matching `^https?://` → `P_REVIEW_MODE=api` (the PR variant,
  unchanged); anything else non-empty → `P_REVIEW_MODE=api-scale` with
  `P_CLOSURE_PACKAGE="$C_PR"`, `P_INTEGRATION_REF="$C_BRANCH"`.
- **The worker positions its own worktree** — the api claim path spawns
  in the shared clone and owns its checkout choreography (the
  established api-mode contract; the gh scale path's dispatcher-side
  checkout has no counterpart here). The `api-scale` block orders it
  before ORIENT: `git fetch origin <INTEGRATION_REF>` and check it out
  (a fetch that fails is a hard stop → park naming the ref, exactly as
  the PR variant treats an unfetchable base); `BASE_REF` is the repo's
  **default branch** — what a recomposition epic merges into — not the
  PR-derived UNRESOLVED sentinel.
- A scale claim whose `branch` is empty parks exactly as today (the
  integration ref is the one binding with no fallback), except the park
  is now the *edge case*, not the whole variant — and it fires as an
  **explicit empty-binding check before the fetch**, not through fetch
  failure: bare `git fetch origin` with an empty ref can SUCCEED
  (configured refs), deferring the failure to a checkout of `origin/`
  with no park note naming the real gap. Under api-scale a BRANCHLESS
  epic therefore PARKS — the gh path's no-aggregate-range fallback
  (per-child ranges from the closure package, `SCALE_RANGE_NOTE`,
  pre-fetched pull refs) has no api twin, and the empty-ref check
  catches exactly the claim such an epic produces (an architect records
  `--branch` only when the composition has an integration ref). The two
  clauses this section previously held simultaneously — "empty branch
  parks" and "the per-child fallback remains" — were contradictory;
  park wins as the amended, safe instruction, and per-child scale
  review on an API board is a **deferred capability** (§Deferred).
- `SKILL.md`'s api-mode entry section: the "an event id, not a URL →
  NOT executable … park needs-human" paragraph is replaced with the
  scale-variant entry: `CLOSURE_PACKAGE` / `INTEGRATION_REF` bindings
  are dispatch-provided; the **Scale review** section governs; verdicts
  (`done` on clean — legal under R1 as the qagent epic close with the
  run's stamped package — or corrective child + `ready-for-architect`)
  work over `{{BOARD_SCRIPTS}}` exactly as the section already states.

**The headline needs no close-path code.** `board-transition.sh` api
mode already sends the edge; R1 made the server accept a qagent run's
leaf `in-review → done` when `pr_url` is a URL. The client-visible
consequence worth documenting where workers read it: a LEAF's
`in-progress → in-review` entry now REQUIRES a `^https?://`-shaped
`--pr` (the implementing SKILL's dispatch sends real PR URLs, so this is
transparent in practice; any caller sending a bare string is refused at
entry with a message naming the requirement).

### 7. Successor `parentPin` — `_sweep_api.sh`

The `claim-successor` exchange reads `out.get("parentPin")` and emits it
flattened in the dispatchers' exact format
(`#<parent_id> @ event <parent_event_cursor>`, empty when null). Two
consumers:

- **`_stamp_lane` grows an optional pin argument** and writes
  `parent_pin` into the delivered worker's registry meta (the same key
  both dispatchers stamp). `_stamp_lane` is the one stamp point BOTH
  delivery branches share — it runs after `board-bind.sh` for the
  resumed-session leg and the fresh-spawn leg alike — so stamping there
  covers the fallback branch that `_persist_successor` never touches
  (`_persist_successor` runs only when a session locator exists, and
  `board-bind.sh` writes no `parent_pin`). Same durability class as the
  lane itself, which is stamped at the same point.
- `_successor_prompt` gains one line when the pin is non-empty —
  `Parent pin (your run's parent-contract window): #N @ event C` — with
  the same rationale the fresh-dispatch path records: no read a worker
  may make hands the pin over, so it travels with the delivery or not at
  all.

The fresh-spawn fallback path delivers the same prompt, so it inherits
the line with no extra work; the meta stamp reaches it through
`_stamp_lane`.

### 8. Read parity — `board-show.sh`, `board-map.sh`

- **board-show** api header line adds the new projection columns:
  `branch=… blocked_by=[3 4] relates=[9]` (empty arrays print `[]` —
  a legal, ordinary state).
- **board-map** `api_snapshot()` maps `blocked_by` (ids → strings, the
  node shape's currency), `relates` → `relates_to`, and `branch`.
  Dependency and relates edges render on api boards. The **ELIGIBLE cue
  stays off for api nodes**: `B.eligible`'s blocker rule requires every
  blocker `done`, while the server's claim predicate treats `wontfix`
  blockers as satisfied too (and adds lane/epic/ownership terms) — a
  client-rederived cue would tell an operator a claimable ticket is
  waiting. `board-list.sh` already declines this exact rederivation in
  api mode; the map does the same, and its table says eligibility is
  the server's answer. The cue's whole surface goes silent together
  (Task 8 flow-back): the `waiting: #N` label suffix is the same
  client-rederived blocker claim and is gated off with it, and the
  dispatchable card class becomes `s_lane` (in neither CLASS nor BADGE)
  so the template's `s_wait` badge — literal text "waiting" — cannot
  keep asserting what the prose stopped claiming. The honesty note
  lives in BOARD.md (BOARD.html is template+JSON, no prose slot). The
  docstring's caveat names the remaining honest gaps — corrected by
  review: the projection DOES carry `pr_url` (it renders); what is
  missing is the GitHub-linked `prs` list and merge state (so no
  close-candidate derivation), `spawned_by`, issue URLs, and
  timestamps.

### Deferred

- **Per-child scale review under api-scale** (Task 6 flow-back): a
  branchless recomposition epic (integration branch deleted as children
  merged) parks needs-human on an API board; gh mode reviews it via
  closure-package per-child ranges. Needs: the dispatcher reading the
  closure package at claim time (or the worker deriving ranges from it)
  plus pull-ref fetching — build when a real API board hits the park.

### Out of scope (stays on dp#51)

The issue body's non-consumption deferrals: gh-path `board-answer.sh`
qagent role fallback; successor-claim escalation counter; queue
pagination; bootstrap-prompt comparison fence; integration-drill
cosmetics. Each is independent of arkho#7 and keeps its own judgment.
Also out: binding `pr`/`branch` into implement-lane dispatch prompts
(nothing consumes them yet), and any `--surface` api support
(server-side pick order is its own A2-side requirement).

## Testing

Two tiers, the A2 pattern:

- **Unit (mock):** `tests/claude-code/board-api/` gains
  `test-edge-verbs.sh` (edge/parent/relates/priority/body against
  fixture responses: success shapes, `noop` flags, and refusal envelopes
  observed from the real service — including `ticket-owned` naming a
  run) and extends `test-register-transition.sh` (note field in the
  logged payload — body free of the question; non-park note lands as a
  comment request; spike→ready-for-architect emits no divergence note)
  and `test-review-dispatch-claim.sh` (scale claim: `P_CLOSURE_PACKAGE`
  / `P_INTEGRATION_REF` reach the render; URL claim: PR variant
  unchanged) and `test-sweep-resume.sh` (successor meta carries
  `parent_pin`; prompt carries the pin line; null pin ⇒ neither).
  Fixture request logs are the assertion surface for payload shape.
- **Integration (real service):** the harness runs the merged arkho
  main, so the new routes are live. One drill extension covering the
  end-to-end headline: register → transition with URL pr → qagent claim
  → `done` as the run actor (leaf close commits); plus one human-verb
  pass (block → claim refuses to draw → unblock → priority → relates →
  body edit refused while owned, committed after release).

## Acceptance

Behavior-phrased; each check names its command. All api-mode checks run
against the integration harness (`harness.sh start`; env from
`.harness/env.sh`) except the last, which runs against production.

1. `board-edge.sh <a> --block <b>` commits a blocked-by edge the next
   `GET /tickets` shows in `blocked_by`; `--unblock` cuts it;
   `--parent`/`--orphan` move lineage; a cycle attempt prints the
   server's `edge-cycle — …` message and exits non-zero.
2. `board-priority.sh <n> P0` prints `#<n>: → P0`; re-running prints
   `(noop)` and the fixture/service log shows no second event.
3. `board-relate.sh <a> <b>` relates; both tickets' `GET /tickets` rows
   report each other; `--cut` from the OTHER endpoint cuts the same
   edge.
4. `board-body.sh <n> --body-file f` rewrites the body; against an
   owned ticket it prints `ticket-owned — …` naming the run and exits
   non-zero. In gh mode the `board:meta` block survives **byte-for-byte
   including noncanonical spelling**: a fixture body carrying an unknown
   future key, a comment line, and odd whitespace in the block comes
   through the edit unchanged.
5. `board-register.sh "t" bug P1 --state needs-human --note "q?" --body-file spec.md`
   sends `note` and `body` as separate payload fields (request log —
   the body free of the question), and in the integration tier the
   birthed decision park's question is `q?` verbatim on
   `GET /queue/decisions`. (Not asserted through `board-show.sh`: the
   ticket projection carries no `park_note` and the register event body
   carries none either — the decisions queue is where the pinned
   contract exposes the standing question.)
6. `board-register.sh "spike t" spike P2 --state ready-for-architect --body-file s.md`
   succeeds with no divergence note anywhere in the output.
7. A qagent claim on an epic carrying a closure package renders the
   **final spawned prompt** from the `api-scale` block: it carries the
   scale framing, `CLOSURE_PACKAGE` = the event id, `INTEGRATION_REF` =
   the branch, the fetch/checkout order, and NO PR-resolution
   instructions; a URL claim renders the `api` block unchanged
   (dispatch dry assertion on the rendered prompt, unit tier).
8. A successor claim whose response carries `parentPin` produces a
   registry meta with `parent_pin: "#N @ event C"` and a delivery prompt
   containing that pin line — asserted on **both** delivery branches
   (resumed session AND the fresh-spawn fallback), and a null pin
   produces neither.
9. `board-show.sh <n>` (api) prints `branch=`, `blocked_by=`,
   `relates=`; `board-map.sh --write` renders a dependency edge between
   two api-board tickets, with no ELIGIBLE cue on api nodes.
10. Full suites green: `tests/claude-code/board-api/` unit tier, the
    integration tier under `ARKHO_DIR`, and
    `tests/claude-code/run-skill-tests.sh` + `scripts/lint-shell.sh`.
11. **Live headline (production):** on the production board
    (`arkho-board-service.onrender.com`, credentials from
    `~/.arkho-board/`), a scratch leaf ticket driven
    register → in-progress → in-review (URL pr) → qagent claim →
    run-actor `done` closes; the ticket and its runs are cleaned up
    after.

## Decision Log

- **board-body.sh is a both-modes verb**, not api-only. Rejected:
  api-only (mirrors the asymmetry this pass exists to retire; and the gh
  documented flow has a live meta-clobbering footgun this fixes for
  free). Rejected: teaching register itself to edit bodies (an edit is
  not a registration; separate verb, separate review surface).
- **Scale bindings are dispatcher-passed, worker-consumed.** The claim
  response is the only place the bindings exist run-scoped
  (`CLOSURE_PACKAGE` is the run's stamped package — a later board read
  can drift); SKILL.md's park text itself named "bindings the claim does
  not carry" as the gap. Rejected: worker self-derives from
  `board-show` (now possible for `branch` via item 8, but the package
  must be the run's stamp, and two derivation paths drift).
- **Variant split on URL shape** (`^https?://`), not on parses-as-number.
  The entry-edge guard (arkho#7 final wave) guarantees a leaf's `pr_url`
  is URL-shaped, so shape is the stable discriminator; mirroring the
  server's Number() semantics client-side re-imports the exact
  subtlety (`' 42 '`, `'4.2e1'`) that guard exists to bury.
- **Non-park notes ride the body head**, not a follow-up comment and
  not the `note` field. Rejected: a post-registration comment (rev
  finding — non-atomic: the register commits first, a failed comment
  loses the note behind `duplicate` on retry; and principal-broken: a
  run registering a child cannot comment on it, `comment` being scoped
  to the run's own ticket while `token()` always speaks as the run).
  Rejected: sending `note` unconditionally and letting the server
  refuse (`note-not-applicable` would break the implicit-birth-with-note
  flow that works today). The prepend is atomic, principal-blind, and
  is what the implicit path already does — extended to explicit
  non-park births where the argument is silently dropped today.
- **Edge verbs print the committed op only**, not gh mode's derived
  sweep lines ("now eligible", epic pulls). Those derivations are
  server-side state machinery in api mode; re-deriving client-side to
  decorate output violates thin-client and can lie under concurrency.
- **No client-side cycle/ancestor checks in api mode.** The server's
  guards are the contract, with messages built for humans; duplicating
  the walk client-side is the state-machine half `_board_api.py`'s
  header forbids.
- **`api-scale` is its own render mode**, not bindings smuggled under
  `api`. The template's mode blocks are exclusive by design (neither
  worker reads the other's framing); composing scale framing with the
  api substrate needs a block that carries both, and the dispatcher —
  which alone sees the claim response — owns the split. Rejected:
  worker-side branching off the `api` block (the block's own text
  orders PR resolution; a scale artifact has no PR to resolve).
- **gh body edit splices the raw meta block**, never parse/render.
  Rejected: `parse_meta` + `render_body` (fixed key allowlist +
  canonicalization — an older client would erase a newer version's
  keys and reformat valid blocks; the verb must not interpret what it
  only needs to carry).
- **No ELIGIBLE cue on api map nodes.** Client `B.eligible` and the
  server's claim predicate disagree (done-only vs done|wontfix terminal
  blockers, plus lane/epic/ownership terms the client can't see);
  `board-list.sh` already declines the rederivation in api mode.
  Rejected: patching `B.eligible` to match (it is gh-mode canon, and
  the server predicate has terms no client read exposes).

## Surprises & Discoveries

_(maintained during implementation)_

- The server judges `note-not-applicable` against the **outcome** birth
  state, not the requested one (`src/tickets.js` runs the check on
  `birthState()`'s result) — so the implicit env-issue inversion and the
  client's needs-info demotion both legally carry a note field.
- (adversarial review, pre-implementation) The ticket projection and
  the register event both omit `park_note` — the decisions queue is the
  only read exposing a birth park's standing question; acceptance moved
  there. The bootstrap renderer drops every unselected mode block, so
  scale bindings under `P_REVIEW_MODE=api` render into nothing — hence
  the `api-scale` block. `_persist_successor` runs only when a session
  locator exists and `board-bind.sh` writes no `parent_pin` — the
  fresh-spawn leg needed its own stamp point (`_stamp_lane`). The
  server's terminal-blocker set is `done|wontfix` while client
  `B.eligible` requires `done` — a live eligibility divergence that
  killed the map cue. A run registering a child cannot comment on it —
  which killed the non-park-note-as-comment design.

- (Task 4) The v1.2 fix itself carried a false premise: `META_RE.search`
  is NOT protected by its end-anchor — leftmost-first matching with a
  lazy middle means a prose-quoted marker becomes the match start. The
  shipped splice walks to the RIGHTMOST match. Same investigation
  surfaced a LIVE gh-mode bug outside this scope: `_board.strip_meta`
  (and everything on it — `update_meta`, so every `branch:`/`pr:`/
  `parent-pin:` write) truncates any body whose prose quotes a
  `<!-- board:meta` marker. Filed as its own ticket; `board-body.sh` is
  currently the only immune meta-writer.

## Outcomes & Retrospective

Shipped 2026-08-12 on branch `dp51-a1-consumption` (10 tasks,
subagent-driven, opus workers): all eight consumption items landed —
four human verbs bound (edges/reparent, relates, priority, plus the new
both-modes `board-body.sh`), register's real `note` field with the
non-park body-head rule, the `api-scale` review variant with
dispatcher-split bindings and worker-owned positioning, successor
`parentPin` into meta + prompt, and read parity (show columns, map
edges, eligibility surfaces silenced across ALL consumers). Suites:
13-file unit tier + 8-drill integration tier + gh parity + reviewing-prs
all green; every one of the eight unit-fixture refusal codes confirmed
against the real service. The R1 headline was proven END-TO-END ON
PRODUCTION: scratch leaf #7 driven register → in-progress → in-review
(URL pr) → qagent claim (run 5, `pr`/`branch` bindings echoed) →
run-actor `done` accepted; scratch principal minted and deleted, run
closed by the phase end.

Review yield (what the loop caught that would have shipped): the v1.2
"fixed" splice was itself wrong (leftmost-first regex — Task 4 walked to
the rightmost match) and the investigation surfaced a LIVE gh-mode
truncation bug (dp#60); the killed ELIGIBLE cue survived as a "waiting"
badge one surface over (Task 8); the api-scale bootstrap had three
narrow-clone/ordering holes (final panel + convergence: FETCH_HEAD
checkout, explicit-refspec base fetch, park-after-barrier); a hot-reload
filter could blank an api board with no control to clear it. Two
pre-existing drills had pinned refusal PROSE and broke when arkho grew
diagnostic messages — repaired to pin identifiers.

Gaps/known boundaries: branchless epics park under api-scale (per-child
fallback deferred, §Deferred); BOARD.html's api eligibility chip now
self-gates but map spawned-by/PR-list/timestamps remain unprojected;
`_stamp_lane`'s empty-lane path skips the pin stamp (documented — the
prompt carries it regardless); dp#51's non-consumption deferrals remain
open on the issue.

## Revision Notes

- v1.0 (2026-08-11): initial spec from the dp#51 consumption design
  session.
- v1.1 (2026-08-11): codex adversarial review (gpt-5.6-sol xhigh), six
  findings, all adopted — two with different fixes than recommended:
  non-park notes moved from follow-up comment to body-head prepend
  (atomic + principal-blind, vs the reviewer's server-side-atomicity
  ask, which needs an arkho change this pass doesn't have); scale
  variant got its own `api-scale` render mode with worker-owned
  integration-ref checkout (vs dispatcher-side positioning, which the
  api claim path's shared-clone contract forbids). Straight adoptions:
  raw-splice gh body edit, `_stamp_lane` as the parent-pin stamp point,
  park-question acceptance via the decisions queue, no ELIGIBLE cue on
  api map nodes.
- v1.2.1 (2026-08-11, Task 2 flow-back): §1's "print the same move
  lines the gh half prints" is refined by construction — api mode prints
  the committed op only, in a deliberately SHORTER line: no `(was …)`
  clause on reparent (the old parent is unknowable without a read the
  thin client refuses) and no derived sweep lines (already §1's rule).
  `#a: parent = #b`, `#a: parent cleared` are the canonical api forms.
- v1.2 (2026-08-11): codex plan review (5 findings, all adopted into the
  plan): trailing-block splice via META_RE byte offsets (a first-marker
  find corrupts bodies quoting a marker-like example); explicit
  empty-`INTEGRATION_REF` park BEFORE the fetch (§6 amended — bare
  fetch can succeed on an empty ref); gh body edit reads one issue
  (`gh issue view --json body`), not `B.snapshot()`'s GraphQL sweep;
  scale/URL dispatch test scenarios isolated and lifecycle-complete
  (bind asserted, not just prompt text); the ELIGIBLE kill covers all
  three consumers (label, `s_elig` class, serialized flag).
- v1.2.2 (2026-08-12, post-PR#61 codex review flow-back): §6's api-scale
  base is no longer the dispatcher's `DEFAULT_BRANCH` as authority — the
  resolution ladder can settle on a stale local `origin/HEAD` or, on a
  gh-less machine where `ls-remote` also fails, a literal `main` guess,
  and a guessed base whose branch exists reviews (and can close) the
  epic against the wrong range. The worker now resolves the true default
  from `git ls-remote --symref origin HEAD` before its fetches — the
  same worker-resolves-base symmetry the PR variant already had — and
  parks needs-human when that resolution fails, never falling back; the
  rendered `BASE_REF` is an advisory echo. (Fix 9542ee3c; the review's
  other finding, a trap-quoting claim in board-body.sh, was refuted
  byte-level and by the passing spool-cleanup assertion.)
