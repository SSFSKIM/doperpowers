#!/usr/bin/env bash
# test-comment.sh — board-comment.sh in BOTH bindings.
# API mode rides a real socket against the fixture mock (the request log pins
# what went on the wire, kind included); gh mode rides a stub `gh` on PATH, so
# the two branches are discriminated rather than assumed.
. "$(dirname "$0")/helpers.sh"

# A free port, not a fixed one: this file must survive running beside anything
# else on the machine (same reason as test-client-core.sh).
PORT="$(python3 -c 'import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

FIX="$(mktemp)"; : > "$FIX.log"
cat > "$FIX" <<'JSON'
[{"method":"POST","path":"/tickets/12/comment","status":200,"body":{"eventId":77}}]
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

run_verb() { ( cd "$r" && BOARD_CREDENTIALS_FILE="$CREDS" BOARD_RUN_TOKEN=run-tok "$SCRIPTS/board-comment.sh" "$@" ); }

t "plain comment posts kind=comment" "77" run_verb 12 "[gate] pass — one line"
t "kind=comment in request" '\"kind\": \"comment\"' cat "$FIX.log"

t "typed op carries body json" '\"closure-package\"' \
  bash -c "cd '$r' && BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=run-tok \
    '$SCRIPTS/board-comment.sh' 12 --kind closure-package --json '{\"evidence\":\"e\"}' >/dev/null; cat '$FIX.log'"

t "unknown kind refused client-side" "kind must be one of" \
  run_verb 12 --kind bogus --json '{}'
# A client-side refusal must not have touched the wire on its way to dying.
nt "unknown kind never reached the server" '\"kind\": \"bogus\"' cat "$FIX.log"

# gh mode: no server involved; assert it shells out to gh (stub gh on PATH)
gdir="$(mktemp -d)"; printf '#!/bin/sh\necho GH-CALLED "$@"\n' > "$gdir/gh"; chmod +x "$gdir/gh"
r2="$(mkrepo)"
t "gh mode uses gh issue comment" "GH-CALLED issue comment" \
  bash -c "cd '$r2' && PATH='$gdir:$PATH' BOARD_REPO=o/r '$SCRIPTS/board-comment.sh' 12 'hello'"
t "gh mode marks a typed kind in the body" "[closure-package] {\"evidence\":\"e\"}" \
  bash -c "cd '$r2' && PATH='$gdir:$PATH' BOARD_REPO=o/r '$SCRIPTS/board-comment.sh' 12 --kind closure-package --json '{\"evidence\":\"e\"}'"
# The binding constraint, asserted rather than assumed: API mode never shells
# out to gh — with a stub that would announce itself if it were called.
nt "api mode never invokes gh" "GH-CALLED" \
  bash -c "cd '$r' && PATH='$gdir:$PATH' BOARD_CREDENTIALS_FILE='$CREDS' BOARD_RUN_TOKEN=run-tok \
    '$SCRIPTS/board-comment.sh' 12 'hello'"

finish
