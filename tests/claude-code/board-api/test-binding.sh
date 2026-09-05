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

# ...unless THIS SESSION's own seat record answers it (dp#35). A worker checks
# out the head it was dispatched for, and a head predating the `repo` key
# carries exactly r7's two-key board.json — while `claude --bg` drops the env
# prefix that was meant to pin the key. board-bind.sh stamped `board_repo` onto
# the record when the dispatcher bound this session, so the fact is on disk
# under a name the worker can read off its own environment.
WSESS="beef0000-0000-4000-8000-00000000000a"
seat() {  # seat <board-key> [path] — one record for $WSESS, alone in the registry
  local into="${2:-}"
  [ -n "$into" ] || { rm -f "$DAEMON_HOME"/*.json; into="$DAEMON_HOME/w.json"; }
  printf '{"uuid":"w","current":"%s","board":"%s","board_repo":"from-record",
           "run_id":41,"fence":3,"run_bearer":"b","bind_confirmed":true}\n' \
    "$WSESS" "$1" > "$into"
}
seat "api:https://b.example"
t "a repo-less api head falls back to this session's seat record" \
  "api|https://b.example|$(basename "$r7").env|from-record" \
  probe "$r7" CLAUDE_CODE_SESSION_ID="$WSESS"
# The board is the whole guard. The registry is machine-global and ticket
# namespaces are not: a session bound on another service says nothing about
# which repo THIS checkout speaks for, so the fatal stands rather than a
# neighbour's repo key being adopted silently.
seat "api:https://other.example"
t  "a record from another board is not this checkout's session" \
  "board.json names binding=api but no repo" probe "$r7" CLAUDE_CODE_SESSION_ID="$WSESS"
nt "and its repo key is never borrowed" "from-record" \
  probe "$r7" CLAUDE_CODE_SESSION_ID="$WSESS"
# ...and it waits out a bind still in flight, because _repo_from_own_seat asks
# own_seat() the same question a verb does. The executor lane binds AFTER the
# spawn and has no startup barrier, so the worker's first board command can run
# while the record still names no board — and on a repo-less head that is a
# fatal, not a fallback.
rm -f "$DAEMON_HOME"/*.json
printf '{"uuid":"w","short":"beef0000","status":"working","task":"x"}\n' \
  > "$DAEMON_HOME/w.json"
# Renamed into place, as board-bind.sh does it: a scan that caught a truncated
# record would skip it and read the absence as "the record went away".
( sleep 2
  seat "api:https://b.example" "$DAEMON_HOME/w.tmp"
  mv "$DAEMON_HOME/w.tmp" "$DAEMON_HOME/w.json" ) &
LATE=$!
t "a bind that lands mid-source still names the repo" \
  "api|https://b.example|$(basename "$r7").env|from-record" \
  probe "$r7" CLAUDE_CODE_SESSION_ID="$WSESS"
wait "$LATE" 2>/dev/null || :

# ONE SERVICE, SEVERAL REPOS. The repo guard applies only where the caller
# already HAS a repo to compare — and on a repo-less head it has none, which is
# the whole reason it is asking. So the record's own claim is the answer here,
# even though the same record is refused once this checkout knows its own repo
# (pinned on the client side in test-run-self-location.sh).
seat "api:https://b.example"
t "a repo-less head takes the record's repo, whichever repo that is" \
  "|from-record" probe "$r7" CLAUDE_CODE_SESSION_ID="$WSESS"

# The declared value still outranks it — the record is the LAST resort, after
# the env override and the file.
seat "api:https://b.example"
t "the file's own repo still wins over the record" "|alpha" \
  probe "$r2" CLAUDE_CODE_SESSION_ID="$WSESS"
# A process that declares it is not its session gets nothing from the record —
# the repo key no less than the bearer. The dispatchers and the sweep say this,
# and a tick has its own binding to read a repo from; a neighbouring worker's
# record is not it.
t "a process that is not its session borrows no repo either" \
  "board.json names binding=api but no repo" \
  probe "$r7" CLAUDE_CODE_SESSION_ID="$WSESS" BOARD_NO_SELF_LOCATE=1
# ...AND IT MUST DECLARE IT IN TIME. The binding is resolved at SOURCE time, so
# an export that lands further down the file is a no-op for the one read it was
# meant to close. A tick launched from a bound worker's session, in a checkout
# whose board.json predates the `repo` key, would then take the neighbour's key
# out of that session's record and claim, sweep and end runs against the wrong
# repo — the accident this key exists to prevent, reached by the other channel.
cat > "$STUB/sminos" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$STUB/sminos"
tick() {  # tick <entrypoint> [args...] — run one from the repo-less checkout
  ( cd "$r7" && env PATH="$STUB:$PATH" GH_STUB_MARKER="$MARKER" \
      CLAUDE_CODE_SESSION_ID="$WSESS" SMINOS_CLI="$STUB/sminos" \
      LOCAL_REPO="$r7" "$@" ) 2>&1 || :
}
t "the sweep refuses a repo it could only have borrowed" \
  "board.json names binding=api but no repo" \
  tick "$SCRIPTS/_sweep_api.sh" renew
t "and so does the executor dispatcher" \
  "board.json names binding=api but no repo" \
  tick "$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh" --sweep
t "and the review dispatcher" \
  "board.json names binding=api but no repo" \
  tick "$REPO_ROOT/skills/qa-loops/scripts/review-dispatch.sh" --sweep
rm -f "$DAEMON_HOME"/*.json

# A BLANK IS A BLANK however it is spelled. `[ -n " " ]` is true, so a repo of
# spaces passed the emptiness check and then rode the wire as an encoded blank —
# which the server reads as NO filter, the exact widening the key exists to
# close, and as no name at all on a write. Trimmed before the check, in the file
# and in the env override alike, so both land on the same refusal.
r8="$(mkrepo)"; mkdir -p "$r8/.doperpowers"
printf '{"binding":"api","url":"https://b.example","repo":"   "}' > "$r8/.doperpowers/board.json"
t  "a whitespace-only repo in the file dies like an absent one" \
  "board.json names binding=api but no repo" probe "$r8"
t  "a whitespace-only env override falls back to the file" \
  "|alpha" probe "$r2" "BOARD_REPO=   "
# ...and when there is nothing to fall back to, it dies rather than widening.
t  "a whitespace-only env override with no file repo dies too" \
  "board.json names binding=api but no repo" probe "$r7" "BOARD_REPO=   "
# A declared repo with stray whitespace is a typo, not a different repo: the
# trimmed value is what the client speaks for, so it cannot reach the wire
# percent-encoded as `%20alpha`.
r9="$(mkrepo)"; mkdir -p "$r9/.doperpowers"
printf '{"binding":"api","url":"https://b.example","repo":"  alpha  "}' > "$r9/.doperpowers/board.json"
t "a padded repo resolves trimmed" "|alpha" probe "$r9"

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

# =========================================================================
# THE BINDING DIGEST. $DAEMON_HOME is machine-global and a board is not, so
# every per-board store under that root — the sweep's tick lock, the claim
# journals, the suppressions, the surface locks — is filed under ONE 16-hex
# key derived from the binding. Two bound repos on one Mac then share the root
# and see none of each other's state, and they do so because a single
# expression answers "which binding is this" for every one of those stores.
DH_D="$(mktemp -d)"
digest() {  # digest <repo dir> [VAR=val ...] — the key that repo files under
  local d="$1"; shift
  ( cd "$d" && env DAEMON_HOME="$DH_D" "$@" bash -c \
      ". '$SCRIPTS/_binding.sh'; board_store_dir board-claims" ) || :
}
API_DIGEST="$(python3 -c 'import hashlib
print(hashlib.sha256(b"api:https://b.example|alpha").hexdigest()[:16])')"
GH_DIGEST="$(python3 -c 'import hashlib
print(hashlib.sha256(b"gh:alpha|").hexdigest()[:16])')"
t "an api binding keys off api:<url>|<repo>" "$API_DIGEST" digest "$r2"
t "and the store is that key's subdirectory of the root" \
  "$DH_D/board-claims/$API_DIGEST" digest "$r2"
t "the store directory is created on demand" "yes" \
  bash -c "[ -d '$DH_D/board-claims/$API_DIGEST' ] && echo yes || echo no"
# The url is normalized exactly as the client's api_url() normalizes it, so a
# binding an override spells with a trailing slash files under ONE key rather
# than a second one — the same rule the sweep lock has always applied.
t "a trailing slash in the url is the same binding" "$API_DIGEST" \
  digest "$r2" BOARD_API_URL=https://b.example/
# THE SERVICE IS PART OF THE IDENTITY, not just the repo name: two services
# could each call a repo `alpha`, and a gh-bound `alpha` is a third board
# again. A digest over the repo name alone would merge all of them.
t "a gh binding keys off gh:<owner/name>" "$GH_DIGEST" digest "$r1" BOARD_REPO=alpha
nt "and never collides with an api binding of the same repo name" \
  "$API_DIGEST" digest "$r1" BOARD_REPO=alpha
rm -rf "$DH_D"

finish
