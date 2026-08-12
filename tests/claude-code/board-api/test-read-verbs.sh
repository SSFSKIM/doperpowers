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
# Fixture order is longest-prefix-first: mock-server.py prefix-matches paths, so
# a "/tickets" entry registered ahead of "/tickets/12/timeline" would shadow it.
cat > "$FIX" <<'JSON'
[
 {"method":"GET","path":"/tickets/12/timeline","status":200,
  "body":{"records":[{"source":"board","cursor":"5","observedAt":"t","sourceTime":null,
    "runId":1,"kind":"transition","body":{"note":"n1","from":"a","to":"b","actor":"run:1","actor_kind":"worker"}},
   {"source":"human","cursor":"6","observedAt":"t","sourceTime":null,
    "runId":null,"kind":"answer","body":{"replies":["ship it","and squash the fixups"]}},
   {"source":"board","cursor":"7","observedAt":"t","sourceTime":null,
    "runId":2,"kind":"closure-package","body":{"pr":"none","evidence":"suite green"}}]}},
 {"method":"GET","path":"/tickets","status":200,
  "body":[{"id":3,"title":"T blocker","category":"work","state":"in-progress",
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
           "branch":"feat/x","blocked_by":[3,4,5],"relates":[9]},
          {"id":13,"title":"T two","category":"work","state":"ready-for-implementer",
           "priority":"P2","owner_run":null,"parent":12,"plan":null,"pr_url":null,
           "branch":null,"blocked_by":[],"relates":[]},
          {"id":14,"title":"T three","category":"work","state":"ready-for-architect",
           "priority":null,"owner_run":42,"parent":null,"plan":null,"pr_url":null,
           "branch":null,"blocked_by":[],"relates":[]}]},
 {"method":"GET","path":"/queue/decisions","status":200,
  "body":[{"correlation_id":"evt-9","ticket_id":12,"run_id":41,"species":"board",
           "question":{"note":"pick one"},"raised_at":"t","state":"needs-human","category":"work"}]},
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
DRIFT="$(mktemp -d)"
printf '{"uuid":"abcdef1234567","ticket":"#99","run_id":7}' > "$DRIFT/d1.json"

V() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DHOME" \
        BOARD_CREDENTIALS_FILE="$CREDS" "$SCRIPTS/$1" "${@:2}" ); }
VD() { ( cd "$r" && PATH="$gdir:$PATH" DAEMON_HOME="$DRIFT" \
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
# the title into the priority position.
t "list renders an ungraded ticket" "#14 ready-for-architect - T three" V board-list.sh
# The state argument is a SERVER-side filter in API mode; a branch that dropped
# it would still print a plausible board (the mock answers any /tickets query).
V board-list.sh ready-for-implementer >/dev/null 2>&1 || true
t "list pushes the state filter onto the wire" "/tickets?state=ready-for-implementer" \
  cat "$FIX.log"

# ── show ───────────────────────────────────────────────────────────────────
t "show prints the ticket row with run/plan/pr" "#12 in-progress P1 T one  owner_run=41" \
  V board-show.sh 12
t "show accepts a #-prefixed ref" "[board:5] transition n1" V board-show.sh '#12'
t "show dies on an unknown ticket" "error: no ticket #77" V board-show.sh 77
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
t "reconcile reports needing-resume" "== needing resume ==" V board-reconcile.sh
# Dispatchable = an unowned ticket in a lane queue — two predicates, and the
# fixture has a counterexample for each: #12 is unowned-but-in-flight, #14 is in
# a lane queue but already owned by run 42. Dropping either predicate lights one
# of the two `nt`s below.
t "reconcile lists the unowned lane ticket" "#13 ready-for-implementer P2 T two" \
  V board-reconcile.sh
nt "reconcile never calls an in-flight ticket dispatchable" \
  "#12 in-progress P1 T one" V board-reconcile.sh
nt "reconcile never calls an owned lane ticket dispatchable" \
  "#14 ready-for-architect - T three" V board-reconcile.sh
# The API branch ends by chaining board-lint.sh (parity with the gh branch),
# which is how the local-registry half of the report gets into an otherwise
# server-only answer. Nothing else in this file reads that chain, so deleting
# the line would be invisible; lint's API-mode banner is its signature.
t "reconcile ends with a lint pass" "server-enforced" V board-reconcile.sh

# ── lint ───────────────────────────────────────────────────────────────────
t "lint FAILs a daemon bound to an absent ticket" \
  "FAIL daemon abcdef12 bound to closed/absent ticket #99" VD board-lint.sh
# The exit code is the machine-readable half of lint; `t` only reads output.
if ( VD board-lint.sh >/dev/null 2>&1 ); then
  echo "FAIL lint must exit non-zero on drift"; FAILS=$((FAILS+1))
else echo "ok   lint exits non-zero on drift"; fi
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

# ── an OLDER server: no topology columns at all ────────────────────────────
# `row.get("blocked_by") or []` reads a server that projects nothing exactly
# like a board with no dependencies, and the map then renders a confident,
# edge-free graph over a board that may be entirely blocked. Whole-response
# absence is the detectable case (no row carries either key) and it has to be
# said out loud in the note. Same rows as above with the two keys stripped.
PORT_OLD="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
FIX_OLD="$(mktemp)"; : > "$FIX_OLD.log"
python3 - "$FIX" "$FIX_OLD" <<'PY'
import json, sys
fx = json.load(open(sys.argv[1]))
for entry in fx:
    if entry["path"] == "/tickets":
        for row in entry["body"]:
            row.pop("blocked_by", None)
            row.pop("relates", None)
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
