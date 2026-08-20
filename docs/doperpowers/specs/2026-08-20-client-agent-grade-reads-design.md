# Client Agent-Grade Reads — Design

The board client (the issue-tracker skill's API binding) can enumerate and
fetch tickets, but it cannot **search** them and cannot read a ticket's
**statement of work** without claiming it. Both server capabilities shipped
and are live (arkho#12 → arkho PR #17): a `?q=` websearch filter over
title+body, and an opt-in `?include=body` on the by-id and paged reads
(paged form: explicit `ids`, at most 20 per read, an 8,388,608-octet
serialized budget; both parameters answer `403 forbidden` to any `run`
bearer — for `q` the contract states the class is refused before the
value is judged; for `include` the client never depends on the ordering,
since the §1 guard dies pre-request). This epic teaches the client both reads and
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
  `q` is sent through `urllib.parse.quote(q, safe="")` — not
  `quote_plus`, whose space-as-`+` is a different wire spelling — so the
  server's grammar
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

- An empty, missing, or whitespace-only `<query>` (trimmed before the
  check) is a usage error (stderr usage, exit 2)
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
  `tickets_by_ids(..., include_body=True)`), and hydration completes
  BEFORE any row prints — the module's materializing discipline: a
  mid-hydration death may not leave a half-printed listing. Each
  hydrated hit's body prints indented under its row; hits beyond 20
  stay rows-only and the tail says so. An empty result is an empty
  listing, exit 0.
- **gh arm**: delegates to the proven spelling —
  `gh issue list --state open --limit 200 -R "$BOARD_REPO" --search
  "<query>"` (the explicit `--limit` matters; the default truncates at
  30 silently). `-R` is unconditional: `_lib.sh` resolves `BOARD_REPO`
  from the checkout whenever it is unset, so a conditional spelling is
  unreachable — the `board-comment.sh` precedent.
  In gh mode `--bodies` is a stderr note and the search PROCEEDS
  (gh's search already matches bodies, so the flag's intent is already
  served) — note-and-proceed is what keeps §4's one-route sentence true
  on both bindings. `--states` is refused (stderr note, exit 2): gh's
  OPEN/CLOSED model is not the board's state vocabulary, and no
  cross-binding prose recommends the flag.
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
- The Toolkit table (SKILL.md's verb-discovery surface) gains a
  `board-search.sh` row (usage + one-line behavior, per-binding note),
  and `board-show.sh`'s row is touched up — its API arm now prints the
  body, which the current row does not say.
- Prose edits follow the writing-skills conventions: the fewest words
  that reroute the instruction; no new constraints.

## §5 Mock coverage (`tests/claude-code/board-api/mock-server.py`)

The mock tier is this epic's primary test bed (the integration tier
needs local docker and SKIPs via exit-77 where absent). The mock is
FIXTURE-DRIVEN and stays that way: method + path matching over static
entries, request-logged; it interprets nothing and inspects no bearer.
New coverage is therefore fixture worlds in the new test file plus
request-log assertions, per the paged-reads precedent
(`test-paged-reads.sh`'s world blocks and `paths`/`reqs` helpers):

- a `q=`-bearing path entry answering a contract-shaped envelope
  (the client never interprets match semantics, so a canned answer
  tests everything the client does);
- `ids=…&include=body` entries answering body-carrying rows (and the
  plain-row twins for the parity drill);
- request-log assertions pinning the exact wire spelling: the
  urlencoded `q`, `include=body` present iff requested, the ≤20-id
  chunk boundary.

Run-bearer 403s and unknown-`include` 400s are NOT mocked: a run's
`q`/`include=body` never reaches the wire (the §1 guard dies
pre-request — the drills assert exactly that), an unknown `include`
value is never sent (the helper takes a boolean), and those server
behaviors are already pinned by arkho's own drills. Fixture message
spellings mirror API.md (see Delegated unknowns).

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
  signature); mock fixtures are exercised only through the client under
  test — nothing asserts on the mock itself.
- SKILL.md prose change sanity-checked per writing-skills; full
  `tests/claude-code/run-skill-tests.sh` green; `scripts/bump-version.sh`
  at finish.

## Acceptance

1. On an API-bound repo, `board-search.sh <word>` prints one row per
   ticket the server's `q` filter answers, state visible on every row,
   exit 0; an empty result exits 0 with the header only.
2. `board-search.sh <word> --bodies` additionally prints the bodies of
   the first ≤20 hits indented under their rows, produced by exactly one
   hydration read; a hit beyond 20 stays rows-only and the output says so.
3. In a run context (`BOARD_RUN_TOKEN` set), `board-search.sh` dies
   before any request with the claim-gate message; `board-show.sh` still
   succeeds, printing the claim-served line where the body would be.
4. `board-show.sh <id>` (human/automation) prints header, body, timeline;
   the body is byte-identical to what `board-body.sh` last wrote.
5. On a gh-bound repo, `board-search.sh <word>` delegates to
   `gh issue list --state open --limit 200 -R <repo> --search "<word>"`;
   `--bodies`
   notes on stderr and the search proceeds; `--states` is refused
   (stderr note, exit 2).
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
  State prints on every row so triage stays informed. The gh arm
  keeps the proven open-only spelling deliberately: gh's OPEN/CLOSED
  cannot distinguish `done` from `wontfix`, and the spelling is the
  prose-tested one — the same state-model mismatch that refuses
  `--states` there. Rejected: open-only default (API arm) and
  `--state all` (gh arm).
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
- **`tickets_search` as its own helper** (vs a `q=` parameter on
  `tickets_all`): the separate helper is the claim-gate guard's natural
  home and keeps `tickets_all`'s signature stable for its existing
  callers; the walk plumbing is shared either way. Rejected: parameter
  on `tickets_all` (marginally smaller, guard placement muddier).
- **Prose: one route via the verb** (vs keeping the gh spelling inline):
  the verb owns the binding branch; prose that branches on binding is a
  second, staler copy of that logic.

## Surprises & Discoveries

(running)

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1 (2026-08-20): initial design, approved in session (controlled track).
- v1.2 (2026-08-20): planning-discovered drift (plan verification review
  C3): the gh delegate spelling carries `-R "$BOARD_REPO"`
  unconditionally — `_lib.sh` always resolves the repo in gh mode, so
  the bare spelling was unreachable; §2 and acceptance 5 corrected.
- v1.1 (2026-08-20): independent review (fable) adopted in full — §5
  rewritten fixture-driven (behavioral-mock misread killed; run-403 and
  unknown-include arms dropped as unreachable through the client);
  gh-arm `--bodies` became note-and-proceed so §4's one-route stays
  true, `--states` pinned refuse/exit-2; Toolkit-table row +
  `board-show` row touch-up joined §4; lead's 403-ordering claim scoped
  to `q`; acceptance 1 rephrased to the server-answers grain;
  `quote(q, safe="")`, whitespace-trim arity, hydrate-before-print, and
  the helper-grain Decision Log clause added.
