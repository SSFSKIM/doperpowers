#!/usr/bin/env bash
# test-transcript-diff.sh — spec acceptance 2, honestly. The same protocol walk
# is run TWICE — once in gh mode against a stateful `gh` stub, once in API mode
# against the real A1 service — and the worker-visible surface of each step is
# compared: the argv, the exit status, and the normalized output.
#
# READ THIS BEFORE THE ASSERTIONS. The spec phrases this acceptance as "the
# diff is empty". Against the committed adapter it is NOT empty, and it cannot
# be: five verbs print something the other binding has no way to produce. The
# drill therefore fences the claim at the level the spec's own purpose
# statement makes ("same scripts, same arguments, same refusal vocabulary"),
# and pins the residue:
#
#   STRICT, no allowance     every step's EXIT STATUS is identical — the two
#                            bindings agree, step for step, on what is legal
#                            and what is refused. THIS is the drift fence that
#                            matters: a second client-side copy of the legality
#                            table (the X5 hazard) shows up here first, as an
#                            rc the other side does not answer with.
#                            The argv is compared too, but read what that buys:
#                            both walks iterate ONE `STEPS` array, so the argv
#                            is the drill's own input rather than either
#                            binding's output, and the comparison can only
#                            catch a capture that lost or misaligned a step. It
#                            was never a behavioral fence — before the compared
#                            form became the unsubstituted one it differed only
#                            by each walk's ticket id, which is a way to fail
#                            falsely, not a way to catch drift.
#   NORMALIZED, pinned       what each step PRINTS, with transport tokens
#                            erased. Every surviving difference must be named
#                            in transcript-compare.py's PINNED table with the
#                            reason it is transport-bound; an unnamed one fails
#                            the drill, and so does a named one that stopped
#                            happening.
#   VOCABULARY, asserted     where a refusal is the same refusal, the drill
#                            says so directly: both bindings name the same
#                            illegal edge, the same unknown ticket, the same
#                            missing artifact.
#   THE RELAY PROMPT         the one worker-visible surface that is not a
#                            verb's stdout: what the resumed worker is actually
#                            told. Compared on its own, because it is the
#                            conversation the acceptance is really about.
#
# The residue is reported, not hidden — see the drill's own output and the
# task report. `PINNED-BUT-IDENTICAL` is a failure on purpose: the table is a
# claim about today's adapter, and a stale claim is worse than no claim.
. "$(dirname "$0")/drill-lib.sh"

drill_start
DISPATCH="$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh"
GH_STUB_PY="$DRILL_DIR/gh-stub.py"
COMPARE="$DRILL_DIR/transcript-compare.py"

BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

One ticket, walked twice — once per binding — so the two worker-visible
transcripts can be compared step for step.

## Success criteria

Both walks reach `done`.
MD

# ---- the walk, as data ------------------------------------------------------
# ONE definition, run under both bindings. `%T` is the ticket the walk's own
# first step registered; nothing else differs between the two invocations.
#
# EVERY EDGE HERE IS ONE BOTH CANONS HOLD. The walk used to verdict through
# `confident-ready` and to probe its illegal-edge refusal on
# `needs-human → confident-ready`; that state is retired from this fork's
# machine while A1's LEGAL_ROWS still carries its rows, so both steps now say
# more about the known legality drift than about the adapter. The verdict is
# the `in-review → done` close both sides keep, and the illegal-edge probe
# moved to `in-progress → ready-for-implementer` — refused by gh's LEGAL and by
# A1's legal_transition alike, and refused by NAMING THE EDGE on both sides,
# which is the property the probe is here for.
STEPS=(
  "board-register.sh|transcript diff walk|enhancement|P1|--body-file|$BODY"
  "board-list.sh|ready-for-implementer"
  "board-transition.sh|%T|in-progress"
  "board-comment.sh|%T|[gate] pass — scripted"
  "board-transition.sh|%T|in-review"
  "board-transition.sh|4242|in-progress"
  "board-transition.sh|%T|needs-human|which db?"
  "board-answer.sh|%T|sqlite"
  "board-transition.sh|%T|ready-for-implementer"
  "board-transition.sh|%T|in-review|--pr|https://example.test/pr/1"
  "board-transition.sh|%T|done"
  "board-show.sh|%T"
  "board-list.sh"
)

# walk <repo> <capture-file> <bind-hook> — runs every step, recording argv,
# exit status and the merged output stream (a refusal is worker-visible too).
# The argv is recorded TWICE: as executed, and as written above with `%T` still
# in it. The second is what the comparator compares — the two walks register
# their own tickets and the ids are never equal, so an executed-argv comparison
# would either always fail or have to normalize digits away, and normalizing
# digits would also erase step 6's deliberate literal 4242 (the known-ticket /
# unknown-ticket distinction that step exists to probe). What that comparison
# is NOT is a fence on binding behavior: both sides read the same `STEPS`, so
# it can only catch a capture that dropped or misaligned a step. The exit
# status is the fence (see the header).
# The hook runs once, after the register, with the new ticket id: it is where
# each binding's dispatcher would have bound a worker to the ticket, and the
# park at step 7 needs that binding to be a PAUSE rather than a disposition.
# The dispatch itself is not part of the compared surface — these are the verbs
# a worker and its human run, not the machinery that spawned them.
walk() {
  local repo="$1" cap="$2" hook="$3" i=0 line tid="" out rc
  : >"$cap"
  local -a argv
  for line in "${STEPS[@]}"; do
    i=$((i + 1))
    IFS='|' read -r -a argv <<<"$line"
    local -a call=()
    local a
    for a in "${argv[@]}"; do
      call+=("${a//%T/$tid}")
    done
    rc=0
    out="$( (cd "$repo" && env HOME="$DRILL_HOME" DAEMON_HOME="$DAEMON_HOME" \
      SMINOS_CLI="$SMINOS_CLI" BOARD_CREDENTIALS_FILE="$BOARD_CREDENTIALS_FILE" \
      BOARD_REPO="$GH_STUB_REPO" GH_STUB_STATE="$GH_STUB_STATE" \
      "$SCRIPTS/${call[0]}" "${call[@]:1}") 2>&1 )" || rc=$?
    # `argv` is FORENSIC — what actually ran, for reading a failure back. The
    # comparator reads `argv_raw` and nothing reads `argv`; wiring an assertion
    # to it would be asserting on the ticket id the two walks cannot share.
    T_I="$i" T_RC="$rc" T_OUT="$out" T_ARGV="$(printf '%s\n' "${call[@]}")" \
      T_ARGV_RAW="$(printf '%s\n' "${argv[@]}")" \
      python3 -c '
import json, os
print(json.dumps({"i": int(os.environ["T_I"]), "rc": int(os.environ["T_RC"]),
                  "argv": os.environ["T_ARGV"].splitlines(),
                  "argv_raw": os.environ["T_ARGV_RAW"].splitlines(),
                  "out": os.environ["T_OUT"]}))' >>"$cap"
    if [ "$i" -eq 1 ]; then
      tid="$(printf '%s\n' "$out" | awk 'END{print $1}')"
      "$hook" "$tid"
    fi
  done
  echo "$tid"
}

# ---- side A: gh mode, on the stub board ------------------------------------
# A repo with NO binding file is gh mode, byte-identically to pre-A2.
GH_REPO="$(mkrepo)"; DRILL_REPOS+=("$GH_REPO")
GH_STUB_REPO="drill/board"
GH_STUB_STATE="$DRILL_TMP/gh-state.json"
cat >"$GH_STUB_DIR/gh" <<EOF
#!/usr/bin/env bash
exec python3 "$GH_STUB_PY" "\$@"
EOF
chmod +x "$GH_STUB_DIR/gh"
# gh mode's relay resolves the bound session through the registry — this is the
# meta its dispatcher would have left behind, written directly because the gh
# dispatcher is not part of the compared surface.
GH_SESS=bbbb0001-0000-4000-8000-000000000000
gh_bind() {
  T_DH="$DAEMON_HOME" T_U="$GH_SESS" T_TID="$1" python3 - <<'PY'
import json, os
u = os.environ["T_U"]
json.dump({"uuid": u, "current": u, "name": "gh-walk-worker", "status": "idle",
           "role": "IMPLEMENT", "lane": "implementer", "ticket": os.environ["T_TID"],
           "updated": "2026-08-10T00:00:00Z"},
          open(os.path.join(os.environ["T_DH"], u + ".json"), "w"))
PY
  : >"$PROJECTS/$GH_SESS.jsonl"
}
GH_CAP="$DRILL_TMP/capture-gh.jsonl"
GH_TID="$(walk "$GH_REPO" "$GH_CAP" gh_bind)"
# Nothing below is meaningful without an id, so the empty case dies here rather
# than failing an assertion further down. What the id IS gets asserted against
# the BOARD that holds it, the way the API half asserts through `ticket_state`
# — the want that stood here was the substring `1`, satisfied by every id
# containing a 1 and by a walk that printed nothing but the number.
[ -n "$GH_TID" ] || { echo "FAIL $(basename "$0") — the gh-mode walk registered no ticket"; exit 1; }
gh_ticket() { T_S="$GH_STUB_STATE" T_ID="$1" python3 -c '
import json, os
it = json.load(open(os.environ["T_S"]))["issues"].get(os.environ["T_ID"])
print("#%s %s" % (os.environ["T_ID"], "(no such issue on the stub board)"
                  if it is None else it["title"]))'; }
t "the gh-mode walk registered its ticket on the stub board" \
  "#$GH_TID transcript diff walk" gh_ticket "$GH_TID"

# ---- side B: API mode, on the real service ---------------------------------
# The gh stub stays on PATH and stays armed: nothing in this half may touch it.
mv "$DAEMON_HOME/$GH_SESS.json" "$DRILL_TMP/gh-session-meta.json"
cat >"$GH_STUB_DIR/gh" <<'EOF'
#!/usr/bin/env bash
echo "GH INVOKED $*" >> "$GH_STUB_MARKER"
exit 97
EOF
chmod +x "$GH_STUB_DIR/gh"
REPO="$(api_repo)"
# The API walk's park has to interrupt a BOUND run, exactly as gh mode's does —
# a park with no owner is a DISPOSITION, a different flow with a different
# answer contract. So the hook here is the real dispatcher: it claims the
# ticket the walk just registered, spawns the scripted worker and binds it.
# `status: idle` afterwards only to match the gh meta; the API relay asks
# `sminos sync`, never the record's status.
api_bind() {
  in_repo "$DISPATCH" --sweep >"$DRILL_TMP/dispatch.out" 2>&1 || true
  local uuid run fence bearer
  # Every column gets its own name even where this hook only needs two of them:
  # the row layout is the contract with meta_of_ticket, and a read that dropped
  # columns would silently shift the ones it kept.
  # shellcheck disable=SC2034  # run/fence hold their columns; only bearer is read
  IFS=$'\t' read -r uuid run fence bearer <<<"$(meta_of_ticket "$1")"
  [ -n "$bearer" ] || { echo "the API walk's ticket #$1 was never bound" >&2; return 1; }
  T_P="$DAEMON_HOME/$uuid.json" python3 -c '
import json, os
p = os.environ["T_P"]
m = json.load(open(p)); m["status"] = "idle"
json.dump(m, open(p, "w"), indent=2)'
}
API_CAP="$DRILL_TMP/capture-api.jsonl"
API_TID="$(walk "$REPO" "$API_CAP" api_bind)"
t "the API-mode walk drove the ticket to the same terminal" "done" ticket_state "$API_TID"

nt "the API half never reached the gh CLI" "GH INVOKED" cat "$GH_LOG"

# ---- the comparison --------------------------------------------------------
REPORT="$DRILL_TMP/compare.txt"
python3 "$COMPARE" "$GH_CAP" "$API_CAP" >"$REPORT" 2>&1 || true
sed 's/^/     /' "$REPORT"
t  "every step agreed on its arguments and its exit status" "VERDICT: accounted" cat "$REPORT"
nt "no step diverged outside the pinned table"              "UNEXPECTED-DIVERGENCE" cat "$REPORT"
nt "and no pinned divergence has quietly gone away"         "PINNED-BUT-IDENTICAL" cat "$REPORT"
t  "the register verb is byte-identical modulo the board's address" \
   "STEP 1 IDENTICAL"                                       cat "$REPORT"

# ---- refusal vocabulary ----------------------------------------------------
# The three refusals diverge in SENTENCE (the rule is held on different sides
# of the wire), but a refusal is only the same refusal if it names the same
# thing. That is asserted directly rather than normalized away.
step_out() { T_I="$2" python3 -c '
import json, os, sys
want = int(os.environ["T_I"])
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r["i"] == want:
        print(r["out"])
        break' "$1"; }
step_line() { step_out "$1" "$2" | eol; }
for cap in "$GH_CAP" "$API_CAP"; do
  side=gh; [ "$cap" = "$GH_CAP" ] || side=api
  t "the $side refusal names the illegal edge itself" \
    "in-progress → ready-for-implementer"                    step_out "$cap" 9
done
# THE UNKNOWN TICKET, per side. A bare `4242` is satisfied by the number turning
# up anywhere in either transcript, so each half pins the phrase it actually
# prints around the id — gh resolves the ticket against its snapshot and says so
# (the id ends the line, hence `eol`), the API names the route it refused. The
# refusal IDENTIFIER is deliberately left unpinned here: which code stands behind
# each sentence is step 6's pinned divergence, not this assertion's claim.
t "the gh refusal names the unknown ticket"  "unknown issue: #4242;" step_line "$GH_CAP" 6
t "the API refusal names the unknown ticket" "POST /tickets/4242/transition refused:" \
  step_out "$API_CAP" 6
# The PR requirement is the one refusal whose SENTENCE does not match: gh mode
# explains the requirement and its destination in prose, while the API answers
# with the contract identifier and then the server's own account of the edge.
# (A1 used to raise `pr-required` with no message at all, leaving the client
# echoing the bare identifier; arkho a05b1ac gave every refusal a message.) Both
# refuse the same write for the same reason, and each half is pinned so the one
# that thins out again is visible.
t "gh explains the missing artifact and where it was going" \
  "a PR link is required when moving to in-review"          step_out "$GH_CAP" 5
t "the API names the contract identifier and the edge it refused" \
  "pr-required — in-progress → in-review requires"          step_out "$API_CAP" 5

# ---- the relay prompt: what the resumed worker is actually TOLD ------------
# Not a verb's stdout, and the most important surface here — this is the
# conversation the acceptance is about. The API transcript is found by the
# sentinel, because the session id is the dispatcher's to choose.
GH_PROMPT="$PROJECTS/$GH_SESS.jsonl"
API_PROMPT="$(grep -l 'board-relay answer:' "$PROJECTS"/*.jsonl 2>/dev/null | head -1)"
[ -n "$API_PROMPT" ] || { echo "FAIL $(basename "$0") — the API relay delivered no prompt"; exit 1; }
# Compared FLATTENED, and out of the JSONL: a transcript line is a RECORD, and
# the prompt is the `content` string inside a user-role one — the same thing the
# sweep's delivery proof reads. The two prompts also wrap at different columns,
# and a line break is not something the worker reads as content.
flat() { python3 -c 'import json, sys
out = []
for line in open(sys.argv[1], errors="replace"):
    try:
        r = json.loads(line)
    except ValueError:
        out.append(line); continue
    c = (r.get("message") or {}).get("content")
    if r.get("type") == "user" and isinstance(c, str):
        out.append(c)
sys.stdout.write(" ".join(" ".join(x.split()) for x in out))' "$1"; }
for side in gh api; do
  file="$GH_PROMPT"; [ "$side" = gh ] || file="$API_PROMPT"
  t "the $side relay tells the worker its park was answered" \
    "was answered by the human." flat "$file"
  t "the $side relay demands a re-stated gate verdict" \
    "Re-state your gate verdict against" flat "$file"
  t "the $side relay names the same comment shape" \
    '("[gate] re-pass — <one line>"' flat "$file"
  t "the $side relay carries the PLAN-EXECUTION carve-out" \
    "PLAN-EXECUTION, which ran no gate, restates plan-execution status instead)" flat "$file"
  t "the $side relay offers the same alternative to a re-pass" \
    "if the answers reshape the work's scope, then proceed under your original protocol." \
    flat "$file"
  t "the $side relay forbids building on stale momentum" \
    "Never build on momentum past an answer that changed the work's shape." flat "$file"
  t "the $side relay carries the human's words verbatim" "sqlite" flat "$file"
done
# ...and every place they differ, pinned in both directions so neither can
# drift silently. The first two are transport (a delivery marker the API relay
# needs and gh mode has no use for; where the answers live). The last is not
# transport at all — it is two authors writing the same sentence differently,
# which is exactly the drift this drill exists to keep visible.
t  "only the API relay carries a delivery sentinel"  "[board-relay answer:" cat "$API_PROMPT"
nt "gh mode has none — the ticket is the record"     "[board-relay answer:" cat "$GH_PROMPT"
t  "only gh mode points the worker back at the ticket for the answers" \
   "the ticket remains the record"                   flat "$GH_PROMPT"
nt "the API relay does not — the answer is not a comment there" \
   "the ticket remains the record"                   flat "$API_PROMPT"
t  "gh phrases the park alternative as 'a fresh park'" \
   "or a fresh park if the answers reshape"          flat "$GH_PROMPT"
t  "the API phrases the same alternative as 'park fresh'" \
   "or park fresh if the answers reshape"            flat "$API_PROMPT"

finish
