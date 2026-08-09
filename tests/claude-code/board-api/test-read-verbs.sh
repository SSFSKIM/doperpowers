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
    "runId":1,"kind":"transition","body":{"note":"n1","from":"a","to":"b","actor":"run:1","actor_kind":"worker"}}]}},
 {"method":"GET","path":"/tickets","status":200,
  "body":[{"id":12,"title":"T one","category":"work","state":"in-progress",
           "priority":"P1","owner_run":41,"parent":null,"plan":null,"pr_url":null},
          {"id":13,"title":"T two","category":"work","state":"ready-for-implementer",
           "priority":"P2","owner_run":null,"parent":12,"plan":null,"pr_url":null},
          {"id":14,"title":"T three","category":"work","state":"ready-for-architect",
           "priority":null,"owner_run":42,"parent":null,"plan":null,"pr_url":null}]},
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
# Honesty about the thinner snapshot: API v1 exposes no blocked-by, spawned or
# relates edges, so the DAG draws no lines at all and the table has to say so — a
# silently edge-free graph reads as "nothing blocks anything", which is a
# different claim entirely.
t "map declares the missing edge class" "blocked-by: (not exposed by API v1)" map_md
t "map writes BOARD.html too" "T one" map_html
# Parenthood survives normalization, and it renders as an epic BOX rather than an
# edge: #13's parent is #12, so #12 shows up in the `epics` payload. An empty
# epics array means the parent field was dropped.
nt "map renders parenthood as epic boxes" '"epics": []' map_html

# ── the binding constraint ─────────────────────────────────────────────────
all_verbs() {
  V board-list.sh || true; V board-show.sh 12 || true; V board-reconcile.sh || true
  V board-lint.sh || true; V board-map.sh --write || true
}
nt "api mode never invokes gh" "GH-CALLED" all_verbs

finish
