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

# Nothing repo-scoped may be exported. A board script resolves the binding for
# its OWN repo; a descendant that sources only _binding.sh from a DIFFERENT repo
# must re-resolve everything. BOARD_ROOT would come back through the
# honor-if-set branch; BOARD_CREDENTIALS_FILE and BOARD_API_URL would come back
# the same way and leave the child reading its own board.json while holding the
# parent's token file and API URL — a mismatched half-bound state.
CHILD="$STUB/child-root.sh"
printf '#!/usr/bin/env bash\n. "%s/_binding.sh"\nprintf "root=%%s\\ncreds=%%s\\nurl=%%s\\n" \\\n  "$(basename "$BOARD_ROOT")" "$(basename "$BOARD_CREDENTIALS_FILE")" "${BOARD_API_URL:-}"\n' \
  "$SCRIPTS" > "$CHILD"
PARENT="$STUB/parent-root.sh"
printf '#!/usr/bin/env bash\n. "%s/_lib.sh"\ncd "$1" || exit 1\nexec "%s"\n' "$SCRIPTS" "$CHILD" > "$PARENT"
chmod +x "$CHILD" "$PARENT"
# Parent binds r2 (api, url set), child crosses into r1 (gh, no url).
cross() { bash -c "cd '$r2' && exec '$PARENT' '$r1'"; }
t "BOARD_ROOT does not leak into a child in another repo"             "root=$(basename "$r1")"       cross
t "BOARD_CREDENTIALS_FILE does not leak into a child in another repo" "creds=$(basename "$r1").env" cross
nt "BOARD_API_URL does not leak into a child in another repo"         "b.example"                   cross

# Linked worktrees: the credentials slug must name the REPO, not the checkout
# directory. `git rev-parse --show-toplevel` in a worktree is the worktree dir —
# usually a branch name — so a slug taken from it points at a file that was
# never written. The stable identity is the main checkout's directory.
r5="$(mkrepo)"
git -C "$r5" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
WT="$(mktemp -d)/some-feature-branch"
git -C "$r5" worktree add -q "$WT" -b some-feature-branch
t "worktree credentials slug is the main repo, not the worktree dir" \
  "$(basename "$r5").env" \
  bash -c "cd '$WT' && . '$SCRIPTS/_binding.sh' && basename \"\$BOARD_CREDENTIALS_FILE\""

# AN UNKNOWN BINDING IS A CONFIGURATION ERROR, NOT A DEFAULT. Falling through
# left BOARD_BINDING=gh, so a typo silently sent every read and every mutation
# to GitHub — against a repo whose board lives somewhere else entirely.
r6="$(mkrepo)"; mkdir -p "$r6/.doperpowers"
printf '{"binding":"arkho","url":"http://b.example"}' > "$r6/.doperpowers/board.json"
typo_binding() { ( cd "$r6" && . "$SCRIPTS/_binding.sh" && echo "binding=$BOARD_BINDING" ); }
t  "an unknown binding fails loud" 'unknown binding "arkho"' typo_binding
nt "and never silently falls back to gh" "binding=gh"        typo_binding

finish
