#!/usr/bin/env bash
. "$(dirname "$0")/helpers.sh"

# A `gh` stub earlier on PATH than any real gh. It can only fail, and it records
# having been reached in $MARKER — a file, because _lib.sh captures gh's stdout
# into BOARD_REPO and sends its stderr to /dev/null, so no stream survives.
# The marker is what makes _lib.sh's `[ "$BOARD_BINDING" = gh ]` guard testable:
# api-mode probes must leave it empty, gh-mode probes must fill it.
STUB="$(mktemp -d)"; MARKER="$STUB/gh-invoked"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
echo GH_INVOKED >> "$GH_STUB_MARKER"
exit 1
EOF
chmod +x "$STUB/gh"

# probe <repo-dir> [VAR=val ...] — prints what _lib.sh resolved in that repo,
# then whatever the gh stub recorded. BOARD_REPO is NOT pre-set: gh-mode probes
# pass it explicitly (those repos have no remote, and _lib.sh must not die
# before printing), while api-mode probes must run without it — with BOARD_REPO
# set, the gh block is unreachable for a second reason and the guard goes
# untested.
probe() { local d="$1"; shift
  : > "$MARKER"
  ( cd "$d" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" "$@" bash -c \
      ". '$SCRIPTS/_lib.sh'; echo \"\$BOARD_BINDING|\${BOARD_API_URL:-}|\$(basename \"\$BOARD_CREDENTIALS_FILE\")\"" ) || :
  cat "$MARKER"
}

r1="$(mkrepo)"                                   # no binding file -> gh
t "absent file is gh mode" "gh||" probe "$r1" BOARD_REPO=o/r

r2="$(mkrepo)"; mkdir -p "$r2/.doperpowers"
printf '{"binding":"api","url":"https://b.example"}' > "$r2/.doperpowers/board.json"
t  "api binding resolves" "api|https://b.example|$(basename "$r2").env" probe "$r2"
nt "api mode never invokes gh" "GH_INVOKED" probe "$r2"

r3="$(mkrepo)"; mkdir -p "$r3/.doperpowers"
printf '{"binding":"gh"}' > "$r3/.doperpowers/board.json"
t "explicit gh is gh mode" "gh||" probe "$r3" BOARD_REPO=o/r

r4="$(mkrepo)"; mkdir -p "$r4/.doperpowers"
printf '{"binding":"api"}' > "$r4/.doperpowers/board.json"   # api without url
t "api without url dies" "board.json names binding=api but no url" probe "$r4"

t  "env url override wins" "api|https://o.example|" \
  probe "$r2" BOARD_API_URL=https://o.example
nt "env url override never invokes gh" "GH_INVOKED" \
  probe "$r2" BOARD_API_URL=https://o.example

# The other half of the guard: it must not suppress the gh probe in gh mode.
t "gh mode without BOARD_REPO still probes gh" "GH_INVOKED" probe "$r1"

# BOARD_ROOT must not be exported. A board script resolves BOARD_ROOT for its
# own repo; a descendant that sources only _binding.sh from a DIFFERENT repo
# would inherit it through the honor-if-set branch and bind board.json and
# credentials to the parent's repo.
CHILD="$STUB/child-root.sh"
printf '#!/usr/bin/env bash\n. "%s/_binding.sh"\nbasename "$BOARD_ROOT"\n' "$SCRIPTS" > "$CHILD"
PARENT="$STUB/parent-root.sh"
printf '#!/usr/bin/env bash\n. "%s/_lib.sh"\ncd "$1" || exit 1\nexec "%s"\n' "$SCRIPTS" "$CHILD" > "$PARENT"
chmod +x "$CHILD" "$PARENT"
t "BOARD_ROOT does not leak into a child in another repo" "$(basename "$r2")" \
  bash -c "cd '$r1' && BOARD_REPO=o/r exec '$PARENT' '$r2'"

finish
