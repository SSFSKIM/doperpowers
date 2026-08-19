#!/usr/bin/env bash
# test-read-verbs.sh — the five read verbs (list/show/reconcile/lint/map) in API
# mode, against the fixture mock. Assertions are on what each verb PRINTS (the
# operator-facing contract) plus, where it discriminates, what went on the wire.
# A stub `gh` sits on PATH for every call, so "API mode never invokes gh" is
# asserted rather than assumed.
. "$(dirname "$0")/helpers.sh"

# Ephemeral port + readiness poll, not a fixed port and a nap: this file has to
# survive running beside anything else on the machine.
PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
# A real cursor, not a synthetic token: arkho's encodeCursor emits the unpadded
# base64url of the compact JSON keyset, and /tickets orders by (priority,
# created_at, id) — so the token is a TRIPLE and decodeCursor refuses any other
# arity. This one is ["P1","2026-08-18 04:15:09.123456+00","12"], the keyset of
# the last row on page 1 below.
C1="WyJQMSIsIjIwMjYtMDgtMTggMDQ6MTU6MDkuMTIzNDU2KzAwIiwiMTIiXQ"
# The queue keyset is (raised_at, correlation_id) — a PAIR, and decodeCursor
# refuses a token of the wrong arity for the route. This one is the last row of
# the wake queue's page 1: ["2026-08-18 04:15:09.123456+00","evt-9"].
Q1="WyIyMDI2LTA4LTE4IDA0OjE1OjA5LjEyMzQ1NiswMCIsImV2dC05Il0"
# Fixture order is longest-prefix-first: mock-server.py prefix-matches paths, so
# a "/tickets?limit=200" entry registered ahead of the cursor-bearing one would
# swallow every page-2 request, and a "/tickets/12" entry ahead of
# "/tickets/12/timeline" would shadow the timeline.
#
# ONE BOARD, ONE SHAPE. Every verb in this file reads the paged surface now, so
# the seven rows live in the walk's two pages and nowhere else — there is no
# bare "/tickets" entry left, and a verb that reverted to the whole-board read
# would take the mock's own 404 and die.
# Three rows sit OUTSIDE the walk deliberately: #77 and #99 answer 404 by id
# (show's unknown ticket, lint's drifted daemon), and #55 answers by id while
# appearing on no page at all — the row a mid-walk reprioritization hides, which
# lint's confirm read has to find OPEN rather than recommend retiring.
cat > "$FIX" <<JSON
[
 {"method":"GET","path":"/tickets/12/timeline","status":200,
  "body":{"records":[{"source":"board","cursor":"5","observedAt":"t","sourceTime":null,
    "runId":1,"kind":"transition","body":{"note":"n1","from":"a","to":"b","actor":"run:1","actor_kind":"worker"}},
   {"source":"human","cursor":"6","observedAt":"t","sourceTime":null,
    "runId":null,"kind":"answer","body":{"replies":["ship it","and squash the fixups"]}},
   {"source":"board","cursor":"7","observedAt":"t","sourceTime":null,
    "runId":2,"kind":"closure-package","body":{"pr":"none","evidence":"suite green"}}]}},
 {"method":"GET","path":"/tickets/12","status":200,
  "body":{"id":12,"title":"T one","category":"work","state":"in-progress",
          "priority":"P1","owner_run":41,"parent":null,"plan":null,"pr_url":null,
          "branch":"feat/x","blocked_by":[3,4,5],"relates":[9]}},
 {"method":"GET","path":"/tickets/13","status":200,
  "body":{"id":13,"title":"T two","category":"work","state":"ready-for-implementer",
          "priority":"P2","owner_run":null,"parent":12,"plan":null,"pr_url":null,
          "branch":null,"blocked_by":[],"relates":[]}},
 {"method":"GET","path":"/tickets/55","status":200,
  "body":{"id":55,"title":"T mover","category":"work","state":"in-progress",
          "priority":"P1","owner_run":44,"parent":null,"plan":null,"pr_url":null,
          "branch":null,"blocked_by":[],"relates":[]}},
 {"method":"GET","path":"/tickets/77","status":404,
  "body":{"error":{"code":"not-found","message":"no such ticket: 77"}}},
 {"method":"GET","path":"/tickets/99","status":404,
  "body":{"error":{"code":"not-found","message":"no such ticket: 99"}}},
 {"method":"GET","path":"/tickets?limit=200&states=ready-for-architect,ready-for-implementer",
  "status":200,
  "body":{"items":[{"id":13,"title":"T two","category":"work","state":"ready-for-implementer",
                    "priority":"P2","owner_run":null,"parent":12,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]},
                   {"id":14,"title":"T three","category":"work","state":"ready-for-architect",
                    "priority":null,"owner_run":42,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/tickets?limit=200&states=ready-for-implementer","status":200,
  "body":{"items":[{"id":13,"title":"T two","category":"work","state":"ready-for-implementer",
                    "priority":"P2","owner_run":null,"parent":12,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/tickets?limit=200&cursor=$C1","status":200,
  "body":{"items":[{"id":13,"title":"T two","category":"work","state":"ready-for-implementer",
                    "priority":"P2","owner_run":null,"parent":12,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]},
                   {"id":14,"title":"T three","category":"work","state":"ready-for-architect",
                    "priority":null,"owner_run":42,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/tickets?limit=1","status":200,
  "body":{"items":[{"id":3,"title":"T blocker","category":"work","state":"in-progress",
                    "priority":"P1","owner_run":43,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]}],
          "next":"$C1","as_of":118}},
 {"method":"GET","path":"/tickets?limit=200","status":200,
  "body":{"items":[{"id":3,"title":"T blocker","category":"work","state":"in-progress",
                    "priority":"P1","owner_run":43,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]},
                   {"id":4,"title":"T blocker done","category":"work","state":"done",
                    "priority":null,"owner_run":null,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]},
                   {"id":5,"title":"T blocker wontfix","category":"work","state":"wontfix",
                    "priority":null,"owner_run":null,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[]},
                   {"id":9,"title":"T sibling","category":"work","state":"in-review",
                    "priority":null,"owner_run":null,"parent":null,"plan":null,"pr_url":null,
                    "branch":null,"blocked_by":[],"relates":[12]},
                   {"id":12,"title":"T one","category":"work","state":"in-progress",
                    "priority":"P1","owner_run":41,"parent":null,"plan":null,"pr_url":null,
                    "branch":"feat/x","blocked_by":[3,4,5],"relates":[9]}],
          "next":"$C1","as_of":118}},
 {"method":"GET","path":"/queue/decisions?limit=200&cursor=$Q1","status":200,
  "body":{"items":[{"correlation_id":"evt-21","ticket_id":9,"run_id":44,"species":"board",
                    "question":{"note":"the second question"},
                    "raised_at":"2026-08-18 05:00:00.000000+00","state":"needs-info",
                    "category":"work"}],
          "next":null,"as_of":118}},
 {"method":"GET","path":"/queue/decisions?limit=200","status":200,
  "body":{"items":[{"correlation_id":"evt-9","ticket_id":12,"run_id":41,"species":"board",
                    "question":{"note":"pick one"},
                    "raised_at":"2026-08-18 04:15:09.123456+00","state":"needs-human",
                    "category":"work"}],
          "next":"$Q1","as_of":118}},
 {"method":"GET","path":"/runs/needing-resume","status":200,"body":[]}
]
JSON
python3 "$TESTS_DIR/mock-server.py" "$FIX" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT

wait_for_port() {  # poll rather than sleep — a fixed nap is a flake
  local tries=200
  while [ "$tries" -gt 0 ]; do
    if python3 -c "import socket, sys
sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $1)) == 0 else 1)"; then
      return 0
    fi
    tries=$((tries - 1))
    sleep 0.05
  done
  return 1
}
wait_for_port "$PORT" || { echo "FAIL mock server never listened on $PORT"; exit 1; }

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT" > "$r/.doperpowers/board.json"
# A stub gh that announces itself.
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
# DAEMON_HOME is pinned hermetic — board-lint.sh globs it, and its default is the
# operator's REAL registry ($HOME/.claude/orchestrating-daemons), which would make
# this suite's verdict depend on which daemons happen to live on the machine.
DHOME="$(mktemp -d)"
# Four registries, one per shape of the absence question lint now asks: a
# daemon on a ticket the walk never served AND the board denies by id (retire),
# one on a ticket the walk served as CLOSED (retire, no confirm needed), one
# on a ticket the walk missed but the board still has open (NOT a retire — the
# walk lost a mover, and a recommendation may not stand on that), and one on a
# ticket the walk served as OPEN — the path every healthy daemon takes, and the
# only one of the four where the verdict has to say nothing at all.
DRIFT="$(mktemp -d)"
printf '{"uuid":"abcdef1234567","ticket":"#99","run_id":7}' > "$DRIFT/d1.json"
DCLOSED="$(mktemp -d)"
printf '{"uuid":"c105ed1234567","ticket":"4","run_id":8}' > "$DCLOSED/d2.json"
DMOVER="$(mktemp -d)"
printf '{"uuid":"m0ved1234567","ticket":"#55","run_id":9}' > "$DMOVER/d3.json"
DOPEN="$(mktemp -d)"
printf '{"uuid":"a11ve1234567","ticket":"#12","run_id":10}' > "$DOPEN/d4.json"

V() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DHOME" \
        BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
VD() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DRIFT" \
         BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
VC() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DCLOSED" \
         BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
VM() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DMOVER" \
         BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
VO() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DOPEN" \
         BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
map_md() { V board-map.sh --write >/dev/null; cat "$r/doperpowers/issue-tracker/BOARD.md"; }
map_html() { V board-map.sh --write >/dev/null; cat "$r/doperpowers/issue-tracker/BOARD.html"; }

# ── the brief's five ───────────────────────────────────────────────────────
t "list renders server rows" "#12 in-progress P1 T one" V board-list.sh
t "show prints timeline record" "[board:5] transition n1" V board-show.sh 12
# A1's event bodies are TYPED, not one `note` field. Rendering `note` alone
# printed every human answer, parent impact and closure package BLANK — and
# "read your own ticket timeline FIRST" is a successor's first instruction,
# with this as the only place that history exists.
t "an answer's replies are rendered, not dropped"  "ship it"              V board-show.sh 12
t "including every reply line"                     "and squash the fixups" V board-show.sh 12
t "a typed comment payload is rendered too"        "suite green"          V board-show.sh 12
# One record, one entry: a multi-line reply is INDENTED under its header rather
# than run together, so a continuation cannot read as another record.
t "the continuation is indented under its record"  "    and squash the fixups" V board-show.sh 12
t "reconcile shows wake queue" "pick one" V board-reconcile.sh
t "map --write renders BOARD.md" "T one" map_md
t "lint API mode reports thin scope" "server-enforced" V board-lint.sh

# ── list ───────────────────────────────────────────────────────────────────
# The header is the point of the row format: server order is NOT dispatch order,
# and an operator reading top-down would otherwise assume it is.
t "list marks server order informational" "# dispatch order is server-owned in API mode" \
  V board-list.sh
t "list renders every server row" "#13 ready-for-implementer P2 T two" V board-list.sh
# A null priority renders as "-", not as "None" or an empty column that swallows
# the title into the priority position. #14 rides the SECOND page, so this row
# also says the walk ran to `next: null` rather than printing page one.
t "list renders an ungraded ticket" "#14 ready-for-architect - T three" V board-list.sh
# The read itself, off the wire. `"path": "/tickets?limit=200"` carries its
# closing quote: the page-2 request is a longer path and must not satisfy the
# page-1 assertion, and a bare-listing read must not satisfy either.
: > "$FIX.log"
V board-list.sh >/dev/null
t "list opts into the paged envelope" '"path": "/tickets?limit=200"' cat "$FIX.log"
t "and carries the server's cursor back verbatim" "cursor=$C1" cat "$FIX.log"
nt "and reads no bare listing beside it" '"path": "/tickets"' cat "$FIX.log"
# The state argument is a SERVER-side filter in API mode; a branch that dropped
# it would still print a plausible board (the mock answers any /tickets query).
# It rides the PROMOTED PLURAL `states=` — the paged surface has no `state=`,
# so a client that kept the singular would be filtering nothing.
: > "$FIX.log"
V board-list.sh ready-for-implementer >/dev/null 2>&1 || true
t "list pushes the state filter onto the wire as the promoted plural" \
  '"path": "/tickets?limit=200&states=ready-for-implementer"' cat "$FIX.log"

# ── show ───────────────────────────────────────────────────────────────────
t "show prints the ticket row with run/plan/pr" "#12 in-progress P1 T one  owner_run=41" \
  V board-show.sh 12
t "show accepts a #-prefixed ref" "[board:5] transition n1" V board-show.sh '#12'
# A junk ref is a caller mistake, and it has to die as one: the by-id route
# cannot be built from it at all, so an unguarded ref surfaces as a traceback
# where the whole-board scan used to answer "no such ticket".
t "show refuses a junk ref the way the gh path does" "not an issue number: abc" \
  V board-show.sh abc
nt "and raises no traceback doing it" "Traceback" V board-show.sh abc
# ONE TICKET, ONE READ. The row comes from GET /tickets/:id — the whole-board
# scan this replaces cost the entire board to answer a single-row question. Both
# assertions carry the closing quote: `"path": "/tickets/12"` is not satisfied
# by the timeline read, and `"path": "/tickets"` matches the bare listing only.
: > "$FIX.log"
V board-show.sh 12 >/dev/null
t "show resolves its ticket by id" '"path": "/tickets/12"' cat "$FIX.log"
nt "and reads no whole board to do it" '"path": "/tickets"' cat "$FIX.log"
# Absence is now the SERVER's answer rather than a scan coming up empty — and
# the client proves the paged surface exists before it believes a 404, since a
# rolled-back server answers the same `not-found` code for an unknown route.
: > "$FIX.log"
t "show dies on an unknown ticket" "error: no ticket #77" V board-show.sh 77
t "and probed the paged surface before trusting that 404" \
  '"path": "/tickets?limit=1"' cat "$FIX.log"
# The projection carries branch and both edge arrays now (arkho#7); the header
# line is the only place an operator sees them in API mode.
t "show prints branch and both edge arrays" "branch=feat/x blocked_by=[3 4 5] relates=[9]" \
  V board-show.sh 12
# No edges is an ordinary state, not a missing column: it prints as [].
t "show prints empty edge arrays as []" "blocked_by=[] relates=[]" V board-show.sh 13
t "show without an argument prints usage" "Usage: board-show.sh" V board-show.sh

# ── reconcile ──────────────────────────────────────────────────────────────
t "reconcile heads the wake queue" "== wake queue (standing parks) ==" V board-reconcile.sh
t "reconcile names the parked ticket and state" "#12 [needs-human] pick one" V board-reconcile.sh
# The wake queue is a WALK now. The second park rides page two, so a client that
# printed the first page would show the human half their standing queue and call
# it the queue.
t "reconcile walks the queue to its last page" "#9 [needs-info] the second question" \
  V board-reconcile.sh
t "reconcile reports needing-resume" "== needing resume ==" V board-reconcile.sh
# Dispatchable = an unowned ticket in a lane queue — still two predicates, but
# they now live on opposite sides of the wire. The LANE half is the server's
# `states=` filter (asserted on the wire below); the UNOWNED half stays here,
# because `owner_run` filters by id only. #14 is the counterexample for the
# client half: in a lane queue, already owned by run 42. The two `nt`s under it
# are the counterexamples for the server half — rows the unfiltered board
# carries that only a client which dropped `states=` could ever print.
t "reconcile lists the unowned lane ticket" "#13 ready-for-implementer P2 T two" \
  V board-reconcile.sh
nt "reconcile never calls an owned lane ticket dispatchable" \
  "#14 ready-for-architect - T three" V board-reconcile.sh
nt "reconcile never calls a closed ticket dispatchable" \
  "#4 done - T blocker done" V board-reconcile.sh
nt "reconcile never calls a ticket in review dispatchable" \
  "#9 in-review - T sibling" V board-reconcile.sh
# The reads themselves, off the wire. `"path": "/queue/decisions"` carries its
# closing quote, so the paged path does not satisfy it — the bare listing does
# and nothing else.
: > "$FIX.log"
V board-reconcile.sh >/dev/null 2>&1 || true
t "reconcile opts the queue into the paged envelope" \
  '"path": "/queue/decisions?limit=200"' cat "$FIX.log"
t "and carries the queue cursor back verbatim" "cursor=$Q1" cat "$FIX.log"
nt "and reads no bare queue listing beside it" '"path": "/queue/decisions"' cat "$FIX.log"
t "reconcile pushes the lane filter onto the wire as the promoted plural" \
  '"path": "/tickets?limit=200&states=ready-for-architect,ready-for-implementer"' \
  cat "$FIX.log"
# The API branch ends by chaining board-lint.sh (parity with the gh branch),
# which is how the local-registry half of the report gets into an otherwise
# server-only answer. Nothing else in this file reads that chain, so deleting
# the line would be invisible; lint's API-mode banner is its signature.
t "reconcile ends with a lint pass" "server-enforced" V board-reconcile.sh

# ── lint ───────────────────────────────────────────────────────────────────
# THE ABSENCE-CONFIRM RULE (spec § Semantics preservation). lint is the one walk
# consumer whose absence drives an ACTION — "retire this daemon" — and walk
# absence is report-grade: a row reprioritized behind an already-passed cursor
# is missing from every page of a COMPLETED walk. So absence is re-asked by id,
# and only the server's 404 is allowed to carry the recommendation.
: > "$FIX.log"
t "lint FAILs a daemon bound to an absent ticket" \
  "FAIL daemon abcdef12 bound to closed/absent ticket #99" VD board-lint.sh
t "and confirmed that absence by id before recommending a retire" \
  '"path": "/tickets/99"' cat "$FIX.log"
# The walk already proved the paged surface for this process, so the by-id 404
# is trusted without the rollback probe — a probe per confirmation would double
# the round trips on a board with a drifted fleet.
nt "and spent no rollback probe doing it" '"path": "/tickets?limit=1"' cat "$FIX.log"
# The other half of the rule: a ticket the walk SERVED as closed is answered
# already. Re-asking by id would be a round trip that cannot change the verdict.
: > "$FIX.log"
t "lint FAILs a daemon bound to a ticket the walk served as closed" \
  "FAIL daemon c105ed12 bound to closed/absent ticket #4" VC board-lint.sh
nt "and re-reads nothing to say so" '"path": "/tickets/4"' cat "$FIX.log"
# The row the walk LOST: absent from every page, alive on the board. The old
# open-id set called this drift and told the operator to retire a daemon doing
# real work; the confirm read is the whole reason it does not.
: > "$FIX.log"
t "a ticket the walk missed but the board still has is no retire candidate" \
  "board-lint: 5 open ticket(s), 0 FAIL" VM board-lint.sh
nt "and no FAIL is printed for it" "FAIL daemon" VM board-lint.sh
t "the by-id confirm is what said so" '"path": "/tickets/55"' cat "$FIX.log"
# The fourth shape, and the one every healthy daemon in the fleet is in: the
# walk SERVED its ticket, open. Three drills above pin what lint must SAY; this
# one pins the far more common case where it must say nothing — a verdict that
# reads the walk-served map with the wrong polarity retires the whole live fleet
# and is invisible to all three. The needle is this daemon's own FAIL line as
# board-lint.sh prints it (uuid[:8] + the ticket), so it cannot pass by matching
# a shape lint never emits.
nt "a daemon on a ticket the walk serves as open is no retire candidate" \
  "FAIL daemon a11ve123 bound to closed/absent ticket #12" VO board-lint.sh
# ...and the positive partner, because the `nt` alone is also satisfied by a
# lint that bailed before reaching a verdict in this world at all.
t "and the DOPEN world still counts five open tickets" \
  "board-lint: 5 open ticket(s), 0 FAIL" VO board-lint.sh
# The exit code is the machine-readable half of lint; `t` only reads output.
if ( VD board-lint.sh >/dev/null 2>&1 ); then
  echo "FAIL lint must exit non-zero on drift"; FAILS=$((FAILS+1))
else echo "ok   lint exits non-zero on drift"; fi
if ( VM board-lint.sh >/dev/null 2>&1 ); then
  echo "ok   lint exits zero when the confirm finds the ticket open"
else echo "FAIL lint must exit zero when the confirm finds the ticket open"; FAILS=$((FAILS+1)); fi
if ( V board-lint.sh >/dev/null 2>&1 ); then echo "ok   lint exits zero when clean"
else echo "FAIL lint must exit zero when clean"; FAILS=$((FAILS+1)); fi

# ── map ────────────────────────────────────────────────────────────────────
t "map renders the ticket row" "| #12 | P1 | in-progress | T one |" map_md
# The projection carries blocked_by and relates now, so both edge classes draw.
# #12 is blocked by #3 (in-progress → active), #4 (done) and #5 (wontfix), and
# relates to #9. These are payload spellings — the template itself contains
# none of them, so the assert reads the render, not the boilerplate.
t "map draws the active dependency edge" '"kind": "block-active"' map_html
t "map draws the satisfied dependency edge" '"kind": "block-done"' map_html
t "map draws the relates edge" '"kind": "relates"' map_html
# SATISFIED IS THE SERVER'S PREDICATE HERE, not the client's: the claim rule
# treats a blocker as cleared when it is TERMINAL — done OR wontfix — so a
# wontfix blocker drawn as a live edge would contradict the very card the
# server is willing to hand out. #4 (done) and #5 (wontfix) are both #12's
# blockers, so exactly two satisfied edges is the fix; one is the gh rule
# leaking into api mode.
done_edge_count() { printf 'satisfied-edges=%s\n' "$(map_html | grep -cF '"kind": "block-done"')"; }
t "a wontfix blocker draws as satisfied in api mode" "satisfied-edges=2" done_edge_count
live_edge_count() { printf 'live-edges=%s\n' "$(map_html | grep -cF '"kind": "block-active"')"; }
t "and only the genuinely unfinished blocker stays live" "live-edges=1" live_edge_count
# The server reports relates symmetrically (#12 relates [9] AND #9 relates
# [12]), so the fixture does too — which makes the renderer's dedupe load-
# bearing: without it the same pair draws twice, one line over the other.
rel_edge_count() { printf 'relates-edges=%s\n' "$(map_html | grep -cF '"kind": "relates"')"; }
t "a symmetric relates pair draws exactly one edge" "relates-edges=1" rel_edge_count
# spawned_by is still unprojected, so that lineage class stays absent — and the
# table has to say so rather than letting a spawned-edge-free graph pass for
# "nothing spawned anything".
t "map declares the still-missing edge class" "spawned-by" map_md
nt "map draws no spawned edges" '"kind": "spawned"' map_html
# The ELIGIBLE cue is server-owned in API mode: B.eligible's blocker rule
# disagrees with the server's claim predicate, so a client-derived cue would
# mislabel a claimable ticket. It feeds THREE surfaces — the Markdown label,
# the card class and the serialized node flag — and all three must read the
# same answer. #13 and #14 are gh-eligible (lane-state leaves, no blockers), so
# a cue still derived on any one surface fires here.
nt "no serialized eligible flag on api nodes" '"eligible": true' map_html
# ...and the flag is OMITTED, not serialized false: `"eligible": false` is an
# assertion this client cannot back, and the page believed it — "0 eligible" in
# the header and an ELIGIBLE-only filter with every card to hide. Key absence is
# what turns those surfaces off (see the template suite). `"eligible":` with the
# colon appears nowhere in the template boilerplate, only in the payload.
nt "the eligible key is absent from api nodes entirely" '"eligible":' map_html
nt "no ELIGIBLE card class on api nodes" '"cls": "s_elig"' map_html
nt "no ELIGIBLE label in the api table" "ELIGIBLE" map_md
# ...and "off" cannot mean falling through to the WAITING class: s_wait's badge
# literally reads "waiting", so a dispatchable api ticket wearing it states the
# very thing the cue is off to avoid. s_lane is in neither the palette nor the
# badge map, so the card degrades to its state name. #13/#14 are the
# dispatchable pair; nothing else in the fixture can wear either class.
t "dispatchable api cards take the badge-less lane class" '"cls": "s_lane"' map_html
nt "no waiting card class on api nodes" '"cls": "s_wait"' map_html
t "the table hands eligibility to the server" "eligibility: server-owned (API mode)" map_md
t "map writes BOARD.html too" "T one" map_html
# Parenthood survives normalization, and it renders as an epic BOX rather than an
# edge: #13's parent is #12, so #12 shows up in the `epics` payload. An empty
# epics array means the parent field was dropped.
nt "map renders parenthood as epic boxes" '"epics": []' map_html
# The parity note is the PROJECTED board's note — the pair below is what makes
# it a claim rather than boilerplate.
nt "a projecting server draws no degradation note" "projects no dependency or relates columns" map_md
# The read itself, off the wire. The graph is drawn from a completed walk; the
# closing quote on `"path": "/tickets"` leaves only a bare whole-board listing
# able to satisfy the negative.
: > "$FIX.log"
V board-map.sh --write >/dev/null 2>&1
t "map walks the paged surface" '"path": "/tickets?limit=200"' cat "$FIX.log"
nt "and reads no whole board to draw the graph" '"path": "/tickets"' cat "$FIX.log"

# ── an OLDER server: no topology columns at all ────────────────────────────
# `row.get("blocked_by") or []` reads a server that projects nothing exactly
# like a board with no dependencies, and the map then renders a confident,
# edge-free graph over a board that may be entirely blocked. Whole-response
# absence is the detectable case (no row carries either key) and it has to be
# said out loud in the note. Same rows as above with the two keys stripped —
# and since the map reads the PAGED surface, the strip targets the envelope
# items of every /tickets page rather than a bare listing that no longer exists.
# The by-id rows are left alone: the map never reads one, and a strip that
# reached them would be describing a server this drill is not about.
PORT_OLD="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
FIX_OLD="$(mktemp)"; : > "$FIX_OLD.log"
python3 - "$FIX" "$FIX_OLD" <<'PY'
import json, sys
fx = json.load(open(sys.argv[1]))
stripped = 0
for entry in fx:
    body = entry.get("body")
    if entry["path"].startswith("/tickets?") and isinstance(body, dict):
        for row in body["items"]:
            row.pop("blocked_by", None)
            row.pop("relates", None)
            stripped += 1
# A silent no-match here would hand the drills below a FULLY PROJECTED board
# wearing the unprojected world's name, and every assertion in it would invert.
assert stripped, "no /tickets page found to strip — the fixture shape moved"
json.dump(fx, open(sys.argv[2], "w"))
PY
python3 "$TESTS_DIR/mock-server.py" "$FIX_OLD" "$PORT_OLD" & MOCK_OLD=$!
trap 'kill $MOCK $MOCK_OLD 2>/dev/null' EXIT
wait_for_port "$PORT_OLD" || { echo "FAIL mock server never listened on $PORT_OLD"; exit 1; }
r_old="$(mkrepo)"; mkdir -p "$r_old/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s"}' "$PORT_OLD" > "$r_old/.doperpowers/board.json"
map_md_old() {
  ( cd "$r_old" && PATH="$gdir:$PATH" DAEMON_HOME="$DHOME" \
      BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/board-map.sh" --write >/dev/null )
  cat "$r_old/doperpowers/issue-tracker/BOARD.md"
}
t "an unprojected board says its topology is unknown" \
  "projects no dependency or relates columns" map_md_old
t "and says so instead of the parity note's edge claim" "NO edge is drawn" map_md_old
nt "the parity note does not also run" "blocked-by and relates draw" map_md_old
t "the tickets themselves still render" "| #12 | P1 | in-progress | T one |" map_md_old

# ── the binding constraint ─────────────────────────────────────────────────
all_verbs() {
  V board-list.sh || true; V board-show.sh 12 || true; V board-reconcile.sh || true
  V board-lint.sh || true; V board-map.sh --write || true
}
nt "api mode never invokes gh" "GH-CALLED" all_verbs

finish
