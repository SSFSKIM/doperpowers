# Client Agent-Grade Reads — Design

The board client (the issue-tracker skill's API binding) can enumerate and
fetch tickets, but it cannot **search** them and cannot read a ticket's
**statement of work** without claiming it. Both server capabilities shipped
and are live (arkho#12 → arkho PR #17): a `?q=` websearch filter over
title+body, and an opt-in `?include=body` on the by-id and paged reads
(paged form: explicit `ids`, at most 20 per read, an 8,388,608-octet
serialized budget; both parameters answer `403 forbidden` to any `run`
bearer, before value judgment). This epic teaches the client both reads and
routes the toolkit's duplicate-registration judgment onto them — replacing
the pre-registration search prose's standing hole: *"an API-bound repo has
no client search verb yet"* (SKILL.md §The ticket body). The gh binding
keeps its proven `gh issue list --search` route, wrapped by the same verb.

Server contract of record: arkho `board-service/API.md` (§1 Boundary
bounds; `GET /tickets` filter table; `GET /tickets/:id`).

## §1 Helpers (`scripts/_board_api.py`)

- `tickets_search(q, states=None, principal="automation")` — complete
  cursor walk of `/tickets?q=<urlencoded>&limit=200[&states=<states>]`,
  same shape as `tickets_all`: report-grade completeness, id-keyed dedupe
  (later data wins), fail-closed walk (`_walk`/`_envelope` unchanged).
  `q` is sent through `urllib.parse.quote` — the server's grammar
  (websearch: unquoted AND, `or`, `-` negation, quoted phrases) rides
  inside one query parameter, never split client-side.
- `ticket(tid, principal="human", include_body=False)` — appends
  `?include=body` when asked; the returned row then carries `body`.
- `tickets_by_ids(ids, principal="human", include_body=False)` — when
  hydrating, chunks at `_MAX_BODY_IDS = 20` (API.md §1) instead of
  `_MAX_IDS = 200`, and appends `&include=body` to each chunk's read.
  Rows carry `body` iff requested — the row spelling is otherwise the
  shared one (server invariant, drilled here as parity).
- **Claim-gate guard.** `token()` speaks as the run whenever
  `BOARD_RUN_TOKEN` is set, and the server refuses `q` and `include=body`
  to run bearers categorically. So the q/body entry points die client-side
  in a run context, before any request, with the reason: a run's statement
  of work arrives in its claim payload, and search is claim-gated because
  a run's `q` would be a term-membership oracle over body text it cannot
  read (arkho#12). One guard helper, called by `tickets_search` and by the
  `include_body=True` arms.
- Budget refusals (`400 invalid-argument` naming the measured total) pass
  through as the server's own message — at this toolkit's body sizes
  (KBs) the 8 MiB budget over ≤20 bodies is not a reachable bound;
  the helper docstring records that judgment rather than code handling it.

## §2 New verb: `scripts/board-search.sh`

    board-search.sh <query> [--states s1,s2] [--bodies]

- An empty or missing `<query>` is a usage error (stderr usage, exit 2)
  — the toolkit's arity-guard convention; the server's blank-`q` 400 is
  never the first line of defense for a caller this client can check.
- **API arm**: `tickets_search` under the automation principal (as are
  the `--bodies` hydration reads). Prints one
  row per hit in server order — `#<id> <state> <priority> <title>` — under
  a header line that says the order is server-owned and the search spans
  ALL states (a `done`/`wontfix` hit is prior-art evidence, which is the
  point of the check; gh's open-only default is deliberately not copied).
  `--states` passes through to the promoted filter. `--bodies` hydrates
  the FIRST ≤20 hits (exactly one budgeted read via
  `tickets_by_ids(..., include_body=True)`) and prints each hydrated
  hit's body indented under its row; hits beyond 20 stay rows-only and
  the tail says so. An empty result is an empty listing, exit 0.
- **gh arm**: delegates to the prose's exact proven spelling —
  `gh issue list --state open --limit 200 --search "<query>"` (the
  explicit `--limit` matters; the default truncates at 30 silently).
  `--states`/`--bodies` are refused with a note in gh mode: gh's search
  already matches bodies, and its state model is not the board's.
- In a run context the API arm dies via the §1 guard before any request.

## §3 `board-show.sh` — the body joins the read (API arm)

`board-show` prints header → **body** → timeline. The body is fetched via
`ticket(tid, include_body=True)` and printed verbatim (it is markdown;
no re-rendering) between the header line and the timeline, separated by
blank lines. This makes the verb's own header comment — "one ticket in
full" — true for the first time: reviewers, sweepers and humans read the
statement of work without a claim, the same one-field read Linear serves
as `issue.description`.

**Run-context degrade**: when `BOARD_RUN_TOKEN` is set the verb omits
`include=body` (the server would 403) and prints one line in the body's
place — `body: claim-served (a run reads its statement of work from the
claim payload)` — so the worker bootstrap's first instruction ("read your
own ticket timeline FIRST") keeps working unchanged.

## §4 Dedup adoption (`SKILL.md` §The ticket body)

The pre-registration search paragraph is re-routed onto the verb:

- One route for both bindings: query each seam identifier with
  `board-search.sh "<function-or-file-name>"` (the verb owns the binding
  branch); triage candidates with `--bodies` where titles are not enough.
- The three-way triage (same defect → comment; same seam → relate;
  cluster tripwire → consolidation) is untouched.
- The gh-specific spelling and the *"no client search verb yet — rely on
  the server's registration-time dedupe until one lands"* sentence are
  replaced. One clause remains for run-context workers: they cannot
  search (claim-gated by design), and the server's registration-time
  dedupe stays their guard.
- Prose edits follow the writing-skills conventions: the fewest words
  that reroute the instruction; no new constraints.

## §5 Mock fidelity (`tests/claude-code/board-api/mock-server.py`)

The mock tier is this epic's primary test bed (the integration tier
needs local docker and SKIPs via exit-77 where absent). The mock gains
the server behaviors the new client code depends on, shaped from the
live contract (API.md + arkho's own drills), per the mock-fidelity rule
(awkward-case raw output, not the caller's shape):

- `q` selects the envelope; matching is a stand-in (substring over
  title+body is acceptable — the CLIENT under test never interprets
  match semantics), but the envelope shape, dispatch order and
  composition with `states`/`ids` are contract-faithful.
- `include=body`: body present iff requested; unknown values →
  `400 invalid-argument`; paged form without `ids` → 400; >20 ids → 400
  (message carrying `at most 20 ids`).
- A run bearer sending `q` or `include=body` → `403 forbidden`, before
  any value judgment (blank `q` from a run is the 403, not the 400).

## Non-goals

- Ranking, highlighting, match counts — A3's search species (arkho#2).
- `q` on `/queue/decisions` — no server surface.
- Bodies in the gh arm, or any gh-side body plumbing.
- Register-integrated advisory hits (auto-search inside
  `board-register.sh`) — the judgment is the agent's; the verb + prose
  route it. Rejected in design (see Decision Log).
- The bare-array retirement patch (arkho#9 item 1) — separate,
  soak-gated.

## Testing

- Mock-tier tests alongside the paged-reads precedent
  (`test-paged-reads.sh`, `test-read-verbs.sh`): helper drills
  (search walk + urlencoding, include_body chunking at 20, body-iff-
  requested row parity, claim-gate guard dies pre-request in run
  context), verb drills (API arm output shape, --bodies first-20 bound,
  gh arm delegation spelling, run-context refusals), show drills (body
  between header and timeline; run-context degrade line).
- Every new drill must fail against the parent commit (naming
  signature); mock additions themselves get contract-shape assertions.
- SKILL.md prose change sanity-checked per writing-skills; full
  `tests/claude-code/run-skill-tests.sh` green; `scripts/bump-version.sh`
  at finish.

## Acceptance

1. On an API-bound repo, `board-search.sh <word>` prints every ticket
   whose title or body matches, one row per hit with state visible, exit
   0; an empty result exits 0 with the header only.
2. `board-search.sh <word> --bodies` additionally prints the bodies of
   the first ≤20 hits indented under their rows, produced by exactly one
   hydration read; a hit beyond 20 stays rows-only and the output says so.
3. In a run context (`BOARD_RUN_TOKEN` set), `board-search.sh` dies
   before any request with the claim-gate message; `board-show.sh` still
   succeeds, printing the claim-served line where the body would be.
4. `board-show.sh <id>` (human/automation) prints header, body, timeline;
   the body is byte-identical to what `board-body.sh` last wrote.
5. On a gh-bound repo, `board-search.sh <word>` delegates to
   `gh issue list --state open --limit 200 --search "<word>"`; `--bodies`
   and `--states` are refused with a note.
6. SKILL.md's pre-registration section names `board-search.sh` as the one
   route on both bindings; the "no client search verb yet" sentence is
   gone; the run-context guard clause is present.
7. The full mock-tier suite and `run-skill-tests.sh` are green; the
   version is bumped via `scripts/bump-version.sh`.

## Delegated unknowns

- Whether an integration-tier drill (real service) is worth adding rides
  on the harness's docker needs — decided at plan time, optional.
- The exact server 400/403 message spellings the mock mirrors are pinned
  during implementation from API.md and arkho's committed drills, not
  invented.

## Decision Log

- **New verb vs `board-list --q`**: a separate `board-search.sh` — search
  is a different consumer story (seam-driven dedup, prior-art), the gh
  world ships it as a separate command too, and `board-list`'s API arm is
  a state-view. Rejected: flag on board-list (would couple two output
  contracts).
- **All-states default** (vs gh's open-only): a terminal hit is prior-art
  evidence — the dedup/prior-art check is exactly where `done` matters.
  State prints on every row so triage stays informed. Rejected:
  open-only default.
- **Body default-on in `board-show`** (vs `--body` flag): the verb's
  charter is "one ticket in full"; Linear's issue view serves the
  description by default. The run-context degrade (claim-served line)
  removes the only breakage risk. Rejected: opt-in flag.
- **Client-side claim-gate die** (vs letting the server 403): `token()`
  makes the outcome deterministic client-side, the die names the design
  reason instead of a bare `forbidden`, and no request is wasted.
  Rejected: server-403 passthrough.
- **`--bodies` bounded to the first 20 hits** (one budgeted read) vs
  hydrating every hit: bounded, legible, and matches the server's own
  read grain (MAX_BODY_IDS); a dedup triage reads a handful anyway.
  Rejected: chunked hydrate-all (unbounded requests off one flag).
- **Budget-400 passthrough** (vs auto-halving chunks): unreachable at
  this toolkit's body sizes; handling it would be speculative code.
  Rejected: fallback logic.
- **Register-integrated advisory** (auto-search in board-register):
  rejected — adds a request to every register, duplicates the agent's
  judgment, and the golden rule (no enforcement beyond the necessary)
  points at prose + verb.
- **Prose: one route via the verb** (vs keeping the gh spelling inline):
  the verb owns the binding branch; prose that branches on binding is a
  second, staler copy of that logic.

## Surprises & Discoveries

(running)

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1 (2026-08-20): initial design, approved in session (controlled track).
