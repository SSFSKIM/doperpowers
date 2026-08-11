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
- **gh mode:** meta-preserving read-modify-write: snapshot the ticket,
  `parse_meta` the current body, `render_body(new_text, meta)`, write
  through `gh issue edit --body-file -`. This is the missing safe
  counterpart to the documented "flesh out the body with
  `gh issue edit`" flow, which clobbers the `board:meta` block today.
  gh mode has no ownership guard (parity with existing gh-mode reality,
  where nothing stops a body edit; the api guard is a server invariant,
  not a client one).

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
  the client's own bodyless demotion to needs-info. The body stays the
  statement of work; the question is stored whole as `park_note`
  server-side, verbatim.
- **A note on a non-park birth** is posted after registration as a
  `POST /tickets/:id/comment` (`kind: "comment"`,
  `text: "[board] note: <note>"`) — gh mode records every note as a
  comment and meta line, and silently dropping the argument in api mode
  (today's behavior for explicit non-park births) loses documented
  input. One extra request, only when a note was given.
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
- Variant split mirrors the server's own discriminator direction, on
  shape: a `pr` matching `^https?://` is the PR variant; anything else
  non-empty is the scale variant. The render gains
  `P_CLOSURE_PACKAGE="$C_PR"` and `P_INTEGRATION_REF="$C_BRANCH"` for
  the scale case (empty/none for the PR case) — `P_REVIEW_MODE` stays
  `api` (one template block; the worker still branches on its entry
  artifact, now with real bindings instead of a park order).
- A scale claim whose `branch` is empty parks exactly as today (the
  integration ref is the one binding with no fallback — its absence is
  the un-derivable case the old park text was about), except the park is
  now the *edge case*, not the whole variant.
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

- `_persist_successor` stamps it into the successor's registry meta as
  `parent_pin` (the same key both dispatchers stamp), so a lane-aware
  resume and the recomposing Architect's lineage check read one format.
- `_successor_prompt` gains one line when the pin is non-empty —
  `Parent pin (your run's parent-contract window): #N @ event C` — with
  the same rationale the fresh-dispatch path records: no read a worker
  may make hands the pin over, so it travels with the delivery or not at
  all.

The fresh-spawn fallback path delivers the same prompt, so it inherits
the line with no extra work.

### 8. Read parity — `board-show.sh`, `board-map.sh`

- **board-show** api header line adds the new projection columns:
  `branch=… blocked_by=[3 4] relates=[9]` (empty arrays print `[]` —
  a legal, ordinary state).
- **board-map** `api_snapshot()` maps `blocked_by` (ids → strings, the
  node shape's currency), `relates` → `relates_to`, and `branch`.
  Dependency and relates edges render on api boards; `B.eligible`'s cue
  works from real edges. The docstring's "no edges at all / ELIGIBLE
  degrades" caveat is rewritten to the remaining honest gaps:
  `spawned_by`, PR linkage, URL, and timestamps are still not projected,
  so spawned-by edges don't render and nodes carry no links/ages.

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
   non-zero. In gh mode it preserves the `board:meta` block byte-for-byte.
5. `board-register.sh "t" bug P1 --state needs-human --note "q?" --body-file spec.md`
   sends `note` and `body` as separate payload fields (request log), and
   `board-show.sh` on the result shows the park question verbatim.
6. `board-register.sh "spike t" spike P2 --state ready-for-architect --body-file s.md`
   succeeds with no divergence note anywhere in the output.
7. A qagent claim on an epic carrying a closure package renders a worker
   prompt whose `CLOSURE_PACKAGE` is the event id and `INTEGRATION_REF`
   the branch (dispatch dry assertion in the unit tier).
8. A successor claim whose response carries `parentPin` produces a
   registry meta with `parent_pin: "#N @ event C"` and a delivery prompt
   containing that pin line.
9. `board-show.sh <n>` (api) prints `branch=`, `blocked_by=`,
   `relates=`; `board-map.sh --write` renders a dependency edge between
   two api-board tickets.
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
- **Non-park notes become comments** rather than being dropped or
  refused client-side. gh parity (gh mode records every note) and the
  established "a documented invocation that silently loses its argument
  is worse than one that fails" rule; letting the server refuse would
  break the implicit-birth-with-note flow that works today.
- **Edge verbs print the committed op only**, not gh mode's derived
  sweep lines ("now eligible", epic pulls). Those derivations are
  server-side state machinery in api mode; re-deriving client-side to
  decorate output violates thin-client and can lie under concurrency.
- **No client-side cycle/ancestor checks in api mode.** The server's
  guards are the contract, with messages built for humans; duplicating
  the walk client-side is the state-machine half `_board_api.py`'s
  header forbids.

## Surprises & Discoveries

_(maintained during implementation)_

- The server judges `note-not-applicable` against the **outcome** birth
  state, not the requested one (`src/tickets.js` runs the check on
  `birthState()`'s result) — so the implicit env-issue inversion and the
  client's needs-info demotion both legally carry a note field.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1.0 (2026-08-11): initial spec from the dp#51 consumption design
  session.
