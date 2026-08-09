#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"

# probe <repo-dir> [VAR=val ...] — prints what _lib.sh resolved in that repo.
# BOARD_REPO is pre-set: gh-mode probes run in repos with no gh remote, and
# _lib.sh must not die before printing.
probe() { local d="$1"; shift; ( cd "$d" && env BOARD_REPO=o/r "$@" bash -c ". '$SCRIPTS/_lib.sh'; echo \"\$BOARD_BINDING|\${BOARD_API_URL:-}|\$(basename \"\$BOARD_CREDENTIALS_FILE\")\"" ); }

r1="$(mkrepo)"                                   # no binding file -> gh
t "absent file is gh mode" "gh||" probe "$r1"

r2="$(mkrepo)"; mkdir -p "$r2/.doperpowers"
printf '{"binding":"api","url":"https://b.example"}' > "$r2/.doperpowers/board.json"
t "api binding resolves" "api|https://b.example|$(basename "$r2").env" probe "$r2"

r3="$(mkrepo)"; mkdir -p "$r3/.doperpowers"
printf '{"binding":"gh"}' > "$r3/.doperpowers/board.json"
t "explicit gh is gh mode" "gh||" probe "$r3"

r4="$(mkrepo)"; mkdir -p "$r4/.doperpowers"
printf '{"binding":"api"}' > "$r4/.doperpowers/board.json"   # api without url
t "api without url dies" "board.json names binding=api but no url" probe "$r4"

t "env url override wins" "api|https://o.example|" \
  probe "$r2" BOARD_API_URL=https://o.example
finish
