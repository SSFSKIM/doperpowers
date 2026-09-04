#!/usr/bin/env bash
# test-bind.sh — board-bind.sh's API branch: the session LOCATOR it posts and
# the run fields it writes back into the daemon registry meta.
#
# Two halves, both asserted against a real socket: what went on the wire (the
# fixture mock's request log) and what landed on disk (the registry meta,
# including its file mode — the meta holds a bearer token at rest).
. "$(dirname "$0")/helpers.sh"

# A free port, not a fixed one: this file must survive running beside anything
# else on the machine (same reason as test-register-transition.sh).
PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
# The refusal body carries the NESTED envelope the service actually writes:
# {"error": {"code": ..., "message": ...}} (API.md §1).
cat > "$FIX" <<'JSON'
[
 {"method":"POST","path":"/runs/41/bind","status":200,"body":{"bound":true}},
 {"method":"POST","path":"/runs/77/bind","status":409,
  "body":{"error":{"code":"fence-stale","message":"run 77 is not current"}}}
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

# A `gh` stub earlier on PATH than any real gh: API mode must never reach it,
# and board-bind's gh-mode half opens with a full board snapshot, so this is
# the assertion that the binding branch actually took. It records into a FILE
# rather than on stdout — _board.gh() captures its child's stdout, so a stub
# that only echoed would be invisible to every assertion here.
STUB="$(mktemp -d)"; MARKER="$STUB/gh-invoked"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
echo GH-CALLED >> "$GH_STUB_MARKER"
exit 1
EOF
chmod +x "$STUB/gh"

statmode() {  # portable "what are this file's permission bits"
  case "$(uname)" in
    Darwin|*BSD) stat -f %Lp "$1" ;;
    *) stat -c %a "$1" ;;
  esac
}

CREDS="$(mktemp)"; printf 'BOARD_AUTOMATION_TOKEN=a\nBOARD_HUMAN_TOKEN=h\n' > "$CREDS"
r="$(mkrepo)"; mkdir -p "$r/.doperpowers"
printf '{"binding":"api","url":"http://127.0.0.1:%s","repo":"testrepo"}' "$PORT" > "$r/.doperpowers/board.json"

# DAEMON_HOME is pinned to a temp dir in every case below — a test that fell
# through to the default would read (and rewrite) the operator's real registry.
DH="$(mktemp -d)"
printf '{"uuid":"u-1234","name":"impl-12","status":"working"}' > "$DH/u-1234.json"
# The predecessor a successor claim hands over from: still marked working,
# still holding the ticket, because the run it belonged to was reaped rather
# than finished. gh mode calls that a live owner and refuses; API mode must
# not, or the recovery path can never rebind the ticket the server just
# reassigned.
# It also still holds ITS bearer at 0600 — the strip below rewrites this file,
# and a rewrite at the default umask would republish that secret.
printf '{"uuid":"u-dead","name":"impl-12-prev","status":"working","ticket":"12","run_bearer":"tok-prev"}' \
  > "$DH/u-dead.json"
chmod 600 "$DH/u-dead.json"
# A NEIGHBOUR REPO'S owner of the SAME ticket number. A bind strips the ticket
# off its prior owners, and ticket numbers are board-local while this registry
# is machine-global — so an unfiltered strip silently unbound a live worker on
# a board this checkout cannot see. Its board key is identical to ours (one
# service, several repos); only the repo stamp separates them.
printf '{"uuid":"u-foreign","name":"impl-12-other","status":"working","ticket":"12",
         "board":"api:http://127.0.0.1:%s","board_repo":"otherrepo"}' "$PORT" \
  > "$DH/u-foreign.json"

printf '{"uuid":"u-nob","name":"nob","status":"working"}' > "$DH/u-nob.json"

bind() {  # bind <uuid-or-prefix> <ticket> [VAR=val ...] — resets the gh marker
  local q="$1" tid="$2"; shift 2
  : > "$MARKER"
  ( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" DAEMON_HOME="$DH" \
      BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_TOKEN=tok-w "$@" \
      "$SCRIPTS/board-bind.sh" "$q" "$tid" )
}

OUT="$(mktemp)"
bind u-12 12 BOARD_RUN_ID=41 BOARD_RUN_FENCE=3 > "$OUT" 2>&1 || true

t  "bind still reports the registry write in API mode" "bound #12 ← u-1234" cat "$OUT"
nt "api bind never invokes gh"                         "GH-CALLED"          cat "$MARKER"

# The locator pinned WHOLE: a substring match on one key survives a payload
# that renamed a key, dropped the session id, or sent the query prefix
# (`u-12`) instead of the resolved daemon uuid.
HOST="$(python3 -c 'import socket; print(socket.gethostname())')"
PROJ="$(basename "$(cd "$r" && git rev-parse --show-toplevel)")"
last_bind_body() {
  grep "\"path\": \"/runs/$1/bind\"" "$FIX.log" | tail -1 |
    python3 -c 'import json, sys; print(json.loads(sys.stdin.read())["body"])'
}
t "locator body pins storeNs / projectKey / sessionId" \
  "{\"storeNs\": \"local:$HOST\", \"projectKey\": \"$PROJ\", \"sessionId\": \"u-1234\"}" \
  last_bind_body 41
# A run context always speaks as the run (the client's token() rule) — the
# locator must not arrive under the automation identity.
t "bind speaks with the run bearer" '"auth": "Bearer tok-w"' cat "$FIX.log"

t "registry meta gains run_id"        '"run_id": 41'         cat "$DH/u-1234.json"
t "registry meta gains the fence"     '"fence": 3'           cat "$DH/u-1234.json"
t "bind_confirmed recorded"           '"bind_confirmed": true' cat "$DH/u-1234.json"
t "the run bearer is stored at rest"  '"run_bearer": "tok-w"' cat "$DH/u-1234.json"
t "ticket ownership still recorded"   '"ticket": "12"'       cat "$DH/u-1234.json"
# Ticket numbers are board-local, the registry is machine-global: the board
# key is what board-transition's live-binding fence matches on (dp#63).
t "registry meta names its board"     '"board": "api:'       cat "$DH/u-1234.json"
# ...AND WHICH REPO ON IT. One service serves several repos out of one ticket
# namespace, so the board key alone does not separate two repos' daemons on one
# machine: their `board` values are identical. Without this the api sweep's
# registry scan renewed and re-bound a NEIGHBOUR's successor — and a re-bind
# overwrites that run's session locator with this repo's projectKey.
t "registry meta names its repo"      '"board_repo": "testrepo"' cat "$DH/u-1234.json"
# The bearer at rest is why the mode matters: the meta sits beside the session
# transcripts and must be no more readable than they are.
t "the meta holding a bearer is 0600" "600" statmode "$DH/u-1234.json"

# The successor handover, the other half of the reaped-predecessor case above:
# the old owner is stripped rather than allowed to veto the rebind.
nt "a reaped predecessor loses the ticket" '"ticket"' cat "$DH/u-dead.json"
# Content, not byte shape: whether the record keeps the compact spelling this
# fixture was written in depends on whether `sminos migrate` (the once-per-
# process preflight in _lib.sh, gated on a legacy root still existing on THIS
# machine) re-rendered it on the way in. What the strip must not do is take
# the ticket or rebind the seat — so the ticket, the repo and the name are
# still the neighbour's, and no run of ours landed on it.
field() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$@"; }
t  "but a neighbour repo's owner of the same number keeps it" "12" \
  field "$DH/u-foreign.json" ticket
t  "and stays the neighbour's"  "otherrepo" field "$DH/u-foreign.json" board_repo
nt "and was not rebound to our run" "run_id" cat "$DH/u-foreign.json"
t  "stripping a predecessor never widens its bearer meta" "600" \
  statmode "$DH/u-dead.json"

# The renew path rebinds a meta whose bind never confirmed, so the ownership
# write runs over a file that ALREADY holds a bearer. End-state pins only: the
# transient widening inside the ownership write is closed by construction
# (mode preservation), and no assertion from outside the process can observe a
# window that narrows again before the command returns.
bind u-1234 12 BOARD_RUN_ID=41 BOARD_RUN_FENCE=3 >/dev/null 2>&1 || true
t "a re-bind leaves the bearer meta at 0600" "600" statmode "$DH/u-1234.json"
# bind_confirmed is already true from the first bind, so it proves nothing about
# THIS run. Count the POSTs instead: only a second server round-trip can produce
# a second /runs/41/bind line in the request log.
bind_posts() { echo "posts=$(grep -c "\"path\": \"/runs/$1/bind\"" "$FIX.log")"; }
t "a re-bind round-trips the server again"   "posts=2" bind_posts 41
t "a re-bind still confirms"                 '"bind_confirmed": true' cat "$DH/u-1234.json"

# A refused bind is not a bind: the meta may not claim confirmation the server
# never gave, or a resume would rehydrate a locator the board does not hold.
# The incumbent is the sharp half — a live daemon already owning #13. The
# server refuses this bind, so the local registry must not have moved either:
# ownership handover is a consequence of the server's verdict, never a
# precondition of asking for it.
printf '{"uuid":"u-77","name":"impl-13","status":"working"}' > "$DH/u-77.json"
printf '{"uuid":"u-inc","name":"impl-13-live","status":"working","ticket":"13"}' \
  > "$DH/u-inc.json"
ticket_of() {  # parsed, not grepped — an untouched file and a rewritten one
  python3 -c 'import json, sys; print("ticket=%s" % json.load(open(sys.argv[1])).get("ticket"))' "$1"
}
RC=0
bind u-77 13 BOARD_RUN_ID=77 >/dev/null 2>&1 || RC=$?
t  "the refused bind did reach the server" '"path": "/runs/77/bind"' cat "$FIX.log"
t  "a refused bind exits nonzero"                "rc=1"             echo "rc=$RC"
nt "a refused bind records no confirmation"      "bind_confirmed"   cat "$DH/u-77.json"
nt "a refused bind stores no bearer"             "run_bearer"       cat "$DH/u-77.json"
t  "a refused bind leaves the incumbent owning #13" "ticket=13" ticket_of "$DH/u-inc.json"
nt "a refused bind hands the caller no ticket"      "ticket"    cat "$DH/u-77.json"

# BOARD_RUN_ID is the dispatcher's half of the contract. Binding without it
# would silently skip the locator POST — the ticket would look bound locally
# while the board could never reach the session. Dying is only half the job:
# the same rule as the refusal above applies, so the registry may not carry a
# handover for a bind that never happened.
printf '{"uuid":"u-nor","name":"impl-14","status":"working"}' > "$DH/u-nor.json"
t "bind without BOARD_RUN_ID dies naming it" "BOARD_RUN_ID" \
  bind u-nor 14
nt "bind without BOARD_RUN_ID confirms nothing" "bind_confirmed" cat "$DH/u-nor.json"
nt "bind without BOARD_RUN_ID moves no ownership" "ticket" cat "$DH/u-nor.json"

# NO BEARER, NO BIND. bind_confirmed is a claim that this meta is COMPLETE —
# that a later relay or successor can rehydrate the worker out of it — and a
# meta holding no run bearer can do none of that. Written anyway, the claim
# silenced the one repair path that could have noticed; the honest answer is a
# loud refusal, before anything reaches the wire.
NOTOK="$(mktemp)"
( cd "$r" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" DAEMON_HOME="$DH" \
    BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_ID=41 BOARD_RUN_FENCE=3 \
    "$SCRIPTS/board-bind.sh" u-nob 16 ) > "$NOTOK" 2>&1 || true
t  "a bearerless bind is refused"           "bind refused for run 41"  cat "$NOTOK"
nt "and confirms nothing"                   "bind_confirmed"           cat "$DH/u-nob.json"
nt "and moves no ownership"                 '"ticket"'                 cat "$DH/u-nob.json"

# The other half of the branch guard: gh mode is untouched by all of the above.
# No board.json, no run env — and the snapshot is still what runs, which is
# only observable through the stub's marker.
r2="$(mkrepo)"
DH2="$(mktemp -d)"
printf '{"uuid":"g-1","name":"gh-one","status":"working"}' > "$DH2/g-1.json"
ghbind() {
  : > "$MARKER"
  ( cd "$r2" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" DAEMON_HOME="$DH2" \
      BOARD_REPO=o/r "$SCRIPTS/board-bind.sh" g-1 9 ) || :
  cat "$MARKER"
}
t "gh mode still goes through gh" "GH-CALLED" ghbind

finish
