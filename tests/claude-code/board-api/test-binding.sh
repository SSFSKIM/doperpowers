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
      ". '$SCRIPTS/_lib.sh'; echo \"\$BOARD_BINDING|\${BOARD_API_URL:-}|\$(basename \"\$BOARD_CREDENTIALS_FILE\")|\${BOARD_REPO:-}\"" ) || :
  cat "$MARKER"
}

r1="$(mkrepo)"                                   # no binding file -> gh
t "absent file is gh mode" "gh||" probe "$r1" BOARD_REPO=o/r

r2="$(mkrepo)"; mkdir -p "$r2/.doperpowers"
printf '{"binding":"api","url":"https://b.example","repo":"alpha"}' > "$r2/.doperpowers/board.json"
t  "api binding resolves" "api|https://b.example|$(basename "$r2").env" probe "$r2"
nt "api mode never invokes gh" "GH_INVOKED" probe "$r2"

# THE REPO THE BINDING SPEAKS FOR. One board service serves several
# repositories out of one ticket namespace, and a client that names none lands
# its writes in the SERVER's founding repo and reads every repo's tickets —
# which is how a register run from a neighbouring checkout filed into this one.
# In api mode BOARD_REPO is the board's repo KEY (in gh mode it stays
# owner/name, resolved by _lib.sh).
t "api binding carries the repo it speaks for" \
  "api|https://b.example|$(basename "$r2").env|alpha" probe "$r2"
t "env BOARD_REPO wins over the file" "|beta" probe "$r2" BOARD_REPO=beta
t "a blank env BOARD_REPO is no declaration at all" \
  "|alpha" probe "$r2" BOARD_REPO=

r3="$(mkrepo)"; mkdir -p "$r3/.doperpowers"
printf '{"binding":"gh"}' > "$r3/.doperpowers/board.json"
t "explicit gh is gh mode" "gh||" probe "$r3" BOARD_REPO=o/r

r4="$(mkrepo)"; mkdir -p "$r4/.doperpowers"
printf '{"binding":"api"}' > "$r4/.doperpowers/board.json"   # api without url
t "api without url dies" "board.json names binding=api but no url" probe "$r4"

# AN api BINDING WITH NO REPO IS A CONFIGURATION ERROR, NOT A DEFAULT. Sending
# no repo makes the SERVER choose one (its founding repo on a write, every repo
# on a read) — the exact silent mis-targeting this key exists to close — so the
# binding refuses before any verb runs rather than falling back to the server's
# pick or to the checkout's directory name.
r7="$(mkrepo)"; mkdir -p "$r7/.doperpowers"
printf '{"binding":"api","url":"https://b.example"}' > "$r7/.doperpowers/board.json"
t  "api without repo dies" "board.json names binding=api but no repo" probe "$r7"
nt "and never guesses one"  "api|https://b.example|"                   probe "$r7"

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
mkdir -p "$r5/.doperpowers"
printf '{"binding":"api","url":"https://b.example","repo":"wt-repo"}' > "$r5/.doperpowers/board.json"
git -C "$r5" -c user.email=t@t -c user.name=t add .doperpowers/board.json
git -C "$r5" -c user.email=t@t -c user.name=t commit -q -m init
WT="$(mktemp -d)/some-feature-branch"
git -C "$r5" worktree add -q "$WT" -b some-feature-branch
t "worktree credentials slug is the main repo, not the worktree dir" \
  "$(basename "$r5").env" \
  bash -c "cd '$WT' && . '$SCRIPTS/_binding.sh' && basename \"\$BOARD_CREDENTIALS_FILE\""
# The repo key rides the CHECKED-IN binding file, so a worktree resolves the
# same one the main checkout does — by construction rather than by a second
# rule. Pinned anyway: it is the property every worker session depends on, and
# the credentials slug above needed its own rule to get there.
t "a worktree speaks for the same repo as its main checkout" "repo=wt-repo" \
  bash -c "cd '$WT' && . '$SCRIPTS/_binding.sh' && echo \"repo=\$BOARD_REPO\""

# AN UNKNOWN BINDING IS A CONFIGURATION ERROR, NOT A DEFAULT. Falling through
# left BOARD_BINDING=gh, so a typo silently sent every read and every mutation
# to GitHub — against a repo whose board lives somewhere else entirely.
r6="$(mkrepo)"; mkdir -p "$r6/.doperpowers"
printf '{"binding":"arkho","url":"http://b.example"}' > "$r6/.doperpowers/board.json"
typo_binding() { ( cd "$r6" && . "$SCRIPTS/_binding.sh" && echo "binding=$BOARD_BINDING" ); }
t  "an unknown binding fails loud" 'unknown binding "arkho"' typo_binding
nt "and never silently falls back to gh" "binding=gh"        typo_binding

finish
