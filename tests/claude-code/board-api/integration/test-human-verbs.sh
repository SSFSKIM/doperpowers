#!/usr/bin/env bash
# test-human-verbs.sh — the dp#51 client bindings against a real A1 service.
#
# The unit tier drives these same verbs against a fixture mock, which answers
# whatever it was told to. This drill is where the answers stop being ours:
# every refusal code, every noop flag and every projection field below is the
# board-service's own, and the drill's whole job is to find out whether the
# client we shipped and the server we shipped against agree.
#
# One flow, because the interesting properties are sequential — an edge gates a
# claim, a claim forbids a body edit, a park birth's note has to stay out of the
# body it was born beside:
#
#   block A on B → the dispatcher passes A over → unblock → the claim draws it
#     → re-grade (and the write-if-changed noop) → relate, cut from the OTHER
#     endpoint → reparent under an epic, then orphan → body edit, refused
#     `ticket-owned` under a run and committed once the run ends → a park BIRTH
#     whose note is the standing question and whose body is untouched → a spike
#     born design-first (R2) → and the R1 headline: a leaf walked to `done`
#     through the qagent lane by the run that claimed it.
#
# The refusal identifiers this drill observes live (`ticket-owned`, `self-edge`,
# `duplicate-edge`, `no-such-edge`) are the ground truth the unit tier's
# fixtures encode. A divergence here is a fixture bug, not a drill bug.
. "$(dirname "$0")/drill-lib.sh"

drill_start
REPO="$(api_repo)"

# A real statement of work per ticket: A1 stores the body as the claim-time
# assignment, and the client refuses a bodyless birth into a lane state.
spec() {  # spec <name> <intent> — writes the file, prints its path
  local f="$DRILL_TMP/$1.md"
  printf '## Problem & intent\n\n%s\n\n## Success criteria\n\nThe drill reaches its assertion.\n' \
    "$2" >"$f"
  echo "$f"
}

# `<id> <url>` on success; a failed birth kills the drill rather than letting a
# later step assert against an empty ticket id.
register() {  # register <title> <category> <priority> [opts...] — prints the id
  local out
  out="$(in_repo "$SCRIPTS/board-register.sh" "$@" 2>&1)" || {
    echo "FAIL $(basename "$0") — register failed: $out" >&2
    exit 1
  }
  printf '%s\n' "$out" | awk 'END{print $1}'
}

# The server's own projection for one ticket, as `k=[v]` lines — GET /tickets is
# the route every one of these fields is published on, so the assertions read
# what a consumer reads. A null prints as `-`: "no parent" is an ordinary
# answer and must be assertable as one. EVERY value is bracketed, scalars
# included: `parent=[9]` cannot be satisfied by the row of a ticket parented
# under #90, which is exactly what the bare `parent=9` allowed.
row() {  # row <ticket>
  api automation GET /tickets | T_ID="$1" python3 -c '
import json, os, sys
tid = os.environ["T_ID"]
t = next((t for t in json.load(sys.stdin) if str(t["id"]) == tid), None)
if t is None:
    sys.exit("no ticket %s on the board" % tid)
def v(k):
    return "-" if t.get(k) is None else t[k]
for k in ("state", "priority", "parent", "branch", "pr_url", "owner_run"):
    print("%s=[%s]" % (k, v(k)))
print("blocked_by=[%s]" % " ".join(str(b) for b in t.get("blocked_by") or []))
print("relates=[%s]" % " ".join(str(x) for x in t.get("relates") or []))'
}

# The standing question the decisions queue publishes for a ticket.
park_question() {  # park_question <ticket>
  api human GET /queue/decisions | T_ID="$1" python3 -c '
import json, os, sys
tid = os.environ["T_ID"]
for r in json.load(sys.stdin):
    if str(r["ticket_id"]) == tid:
        print("question=%s" % (r.get("question") or {}).get("note"))
        break
else:
    print("question=(no row on the queue)")'
}

# A verb that must be REFUSED: its output plus a trailing `rc=<n>`. The exit
# status is half of what a refusal has to get right — a client that printed the
# server's code and then exited 0 would be a silent data-loss bug in any caller
# that branches on `||`.
run_rc() {  # run_rc <cmd...>
  local rc=0 out
  out="$("$@" 2>&1)" || rc=$?
  printf '%s\nrc=%s\n' "$out" "$rc"
}

# The ticket a claim drew, delimited: `drew #1` is a substring of `drew #12`.
drew() { echo "[drew #$1]"; }

end_run() {  # end_run <run-id> — the abandon path, through its own route
  api automation POST "/runs/$1/end" '{"reason":"abandoned"}' >/dev/null
}

# ---- 1. an edge, cut after birth ------------------------------------------
TID_A="$(register "human-verbs leaf A" enhancement P1 \
  --body-file "$(spec a 'Leaf A is the ticket every human verb below is aimed at.')")"
TID_B="$(register "human-verbs leaf B" enhancement P1 \
  --body-file "$(spec b 'Leaf B blocks leaf A, and is the other endpoint of the relates edge.')")"

t "the block edge reports the move it committed" "#$TID_A: blocked_by += #$TID_B" \
  in_repo "$SCRIPTS/board-edge.sh" "$TID_A" --block "$TID_B"
t "and the server's projection carries it" "blocked_by=[$TID_B]" row "$TID_A"

# The client adjudicates none of this: a self-edge is SENT and the server is the
# one that names it. (The unit tier pins the wire; this pins the answer.)
t "a self-edge is the server's refusal, verbatim" "self-edge" \
  run_rc in_repo "$SCRIPTS/board-edge.sh" "$TID_A" --block "$TID_A"
t "an edge that is already there is duplicate-edge" "duplicate-edge" \
  run_rc in_repo "$SCRIPTS/board-edge.sh" "$TID_A" --block "$TID_B"
t "and cutting one that is not is no-such-edge" "no-such-edge" \
  run_rc in_repo "$SCRIPTS/board-edge.sh" "$TID_B" --unblock "$TID_A"

# ---- 2. the edge GATES the dispatcher --------------------------------------
# A is older than B and would be drawn first; blocked, it is passed over, and
# with B taken the lane has nothing left to give.
IFS=$'\t' read -r RUN_B TICK_B _ _ <<<"$(claim_run implementer human-verbs-blocked)"
t "the blocked leaf is passed over for the younger one" "[drew #$TID_B]" \
  drew "$TICK_B"
t "and a blocked ticket is beyond the dispatcher's reach entirely" '"claimed":false' \
  api automation POST /runs/claim \
    "{\"lane\":\"implementer\",\"dispatchNonce\":\"human-verbs-blocked-probe\",\"repo\":\"$(drill_repo_key)\"}"

t "the unblock reports the cut" "#$TID_A: blocked_by -= #$TID_B" \
  in_repo "$SCRIPTS/board-edge.sh" "$TID_A" --unblock "$TID_B"
t "and the projection is empty again" "blocked_by=[]" row "$TID_A"
IFS=$'\t' read -r RUN_A TICK_A _ _ <<<"$(claim_run implementer human-verbs-unblocked)"
t "the same claim now draws the ticket the edge was holding back" "[drew #$TID_A]" \
  drew "$TICK_A"
end_run "$RUN_A"
end_run "$RUN_B"
t "the abandoned run released the ticket" "owner_run=[-]" row "$TID_A"

# ---- 3. the re-grade, and its write-if-changed noop -------------------------
REGRADE="$(in_repo "$SCRIPTS/board-priority.sh" "$TID_A" P0 2>&1)" || true
t  "the re-grade reports the grade that committed" "#$TID_A: → P0" printf '%s\n' "$REGRADE"
nt "a real change is not a noop"                   "(noop)"        printf '%s\n' "$REGRADE"
t "and the board shows it" "priority=[P0]" row "$TID_A"
t "re-sending the standing grade writes nothing, and says so" "#$TID_A: → P0 (noop)" \
  in_repo "$SCRIPTS/board-priority.sh" "$TID_A" P0

# ---- 4. relates: one row, both projections, either end may cut -------------
t "the relate reports the pair" "related: #$TID_A -- #$TID_B" \
  in_repo "$SCRIPTS/board-relate.sh" "$TID_A" "$TID_B"
t "the endpoint written through reports the other" "relates=[$TID_B]" row "$TID_A"
t "and so does the endpoint that was never written"  "relates=[$TID_A]" row "$TID_B"
# THE CUT COMES FROM THE OTHER END, reversed — the edge is normalised, so the
# spelling the client sends is not the spelling the row is stored in.
t "either endpoint may cut it" "cut: #$TID_B -- #$TID_A" \
  in_repo "$SCRIPTS/board-relate.sh" "$TID_B" "$TID_A" --cut
t "the edge is gone from the endpoint that cut it" "relates=[]" row "$TID_B"
t "and from the other one"                         "relates=[]" row "$TID_A"

# ---- 5. lineage: adopt, then orphan ---------------------------------------
# Born design-first so the epic never sits in the executor queue competing
# with A for the claims below.
TID_E="$(register "human-verbs epic E" enhancement P2 --state ready-for-architect \
  --body-file "$(spec e 'Epic E exists to be a parent and then to stop being one.')")"
t "the reparent reports the destination" "#$TID_A: parent = #$TID_E" \
  in_repo "$SCRIPTS/board-edge.sh" "$TID_A" --parent "$TID_E"
t "and the row moves with it" "parent=[$TID_E]" row "$TID_A"
t "the orphan reports the clear" "#$TID_A: parent cleared" \
  in_repo "$SCRIPTS/board-edge.sh" "$TID_A" --orphan
t "and the row has no parent" "parent=[-]" row "$TID_A"

# ---- 6. the body edit, and the run that forbids it -------------------------
BODY2="$(spec a2 'The sharpened statement of work, written while nobody owned the ticket.')"
t "an unowned ticket takes the edit" "#$TID_A: body rewritten" \
  in_repo "$SCRIPTS/board-body.sh" "$TID_A" --body-file "$BODY2"
t "re-sending the standing body writes nothing" "#$TID_A: body rewritten (noop)" \
  in_repo "$SCRIPTS/board-body.sh" "$TID_A" --body-file "$BODY2"

IFS=$'\t' read -r RUN_A2 TICK_A2 _ _ <<<"$(claim_run implementer human-verbs-body)"
t "the P0 ticket is what the lane draws" "[drew #$TID_A]" drew "$TICK_A2"
BODY3="$(spec a3 'The edit that must not reach a worker holding an older assignment.')"
OWNED="$(run_rc in_repo "$SCRIPTS/board-body.sh" "$TID_A" --body-file "$BODY3")"
# The body IS the claim-time assignment: an edit under an open run would reach
# nobody, so the server refuses it and the client must not eat the refusal.
t "an edit under an open run is refused as ticket-owned" "ticket-owned" printf '%s\n' "$OWNED"
t "and the verb exits nonzero"                          "rc=1"          printf '%s\n' "$OWNED"
end_run "$RUN_A2"
t "once the run ends, the same edit commits" "#$TID_A: body rewritten" \
  in_repo "$SCRIPTS/board-body.sh" "$TID_A" --body-file "$BODY3"

# ---- 7. a park BIRTH: the note is the question, not a body prefix ----------
SPEC7="$(spec park 'The statement of work a park birth keeps while its question stands.')"
TID_P="$(register "human-verbs park birth" enhancement P2 --state needs-human \
  --note "which database?" --body-file "$SPEC7")"
t "the birth parks the ticket" "state=[needs-human]" row "$TID_P"
t "the note is the standing question, verbatim" "question=which database?" \
  park_question "$TID_P"
# There is no body read route, so the write-if-changed noop IS the read: a
# re-send of the very file the birth carried can only answer `(noop)` if the
# stored body is that file byte for byte — which is the whole claim, since the
# pre-arkho#7 client prepended the note to the body.
t "and the body is the spec alone — the note was not prepended" \
  "#$TID_P: body rewritten (noop)" in_repo "$SCRIPTS/board-body.sh" "$TID_P" --body-file "$SPEC7"

# ---- 8. a spike born design-first (R2) ------------------------------------
SPIKE="$(in_repo "$SCRIPTS/board-register.sh" "human-verbs spike" spike P2 \
  --state ready-for-architect \
  --body-file "$(spec spike 'A spike whose first act is a design pass.')" 2>&1)" || true
t "the spike is born" "$BOARD_API_URL/tickets/" printf '%s\n' "$SPIKE"
TID_S="$(printf '%s\n' "$SPIKE" | awk 'END{print $1}')"
t "into the architect queue, as R2 rules" "state=[ready-for-architect]" row "$TID_S"
# The client used to warn that this birth diverged from the server; arkho#7
# closed that gap, and the retired warning must not have survived it.
nt "and carries no divergence note" "arkho/issues/7" printf '%s\n' "$SPIKE"

# ---- 9. the R1 headline: a leaf walked to done ----------------------------
TID_L="$(register "human-verbs leaf close" enhancement P1 \
  --body-file "$(spec l 'The leaf that has to reach done through the review lane.')")"
t "the leaf goes in-flight with its working ref" "#$TID_L: → in-progress" \
  in_repo "$SCRIPTS/board-transition.sh" "$TID_L" in-progress --branch feat/human-verbs
t "and the branch is recorded on the row" "branch=[feat/human-verbs]" row "$TID_L"
t "the artifact carries it into review" "#$TID_L: → in-review" \
  in_repo "$SCRIPTS/board-transition.sh" "$TID_L" in-review --pr https://example.test/pr/9
t "with the PR url on the row" "pr_url=[https://example.test/pr/9]" row "$TID_L"

IFS=$'\t' read -r RUN_L TICK_L FENCE_L BEARER_L <<<"$(claim_run qagent human-verbs-close)"
t "the review lane draws the leaf" "[drew #$TID_L]" drew "$TICK_L"
# THE CLOSE IS THE REVIEW RUN'S. A1 grants `in-review → done` to a worker only
# on the qagent lane and only with a URL-shaped pr_url (a numeric one is an
# epic's closure package) — which is exactly the path R1 said this fork's
# Reviewer workers take, and the one the fixture mock could not adjudicate.
t "and the run that claimed it closes it" "#$TID_L: → done" \
  in_repo BOARD_RUN_TOKEN="$BEARER_L" BOARD_RUN_ID="$RUN_L" BOARD_RUN_FENCE="$FENCE_L" \
    "$SCRIPTS/board-transition.sh" "$TID_L" "done"
t "the board shows the leaf closed" "state=[done]" row "$TID_L"

# ---- 10. two repos on one service (dp#33) ---------------------------------
# The board serves several repositories out of ONE ticket namespace, and until
# the binding declared which one a checkout speaks for, the SERVER chose: its
# founding repo on a write, every repo on a list read. Live, that put a register
# run from a neighbouring checkout into this board and printed this board's
# tickets from that one. Two bound repos on one service is the smallest world
# that can tell the difference.
#
# The register row first: a write into a name the service never admitted is
# refused `unknown-repo`, and `board.repo_state` IS that register (the schema
# seeds only the founding repo). Seeded with SQL for the same reason principals
# are — the API publishes no route for it.
sql <<'SQL' >/dev/null
insert into board.repo_state (repo, state) values ('a2-second-repo', 'live')
  on conflict (repo) do nothing;
SQL
REPO2="$(api_repo a2-second-repo)"
in_repo2() { (cd "$REPO2" && env HOME="$DRILL_HOME" DAEMON_HOME="$DAEMON_HOME" \
  SMINOS_CLI="$SMINOS_CLI" BOARD_CREDENTIALS_FILE="$BOARD_CREDENTIALS_FILE" \
  LOCAL_REPO="$REPO2" "$@"); }

SPEC10="$(spec second 'A ticket that belongs to the second repo and nowhere else.')"
OUT2="$(in_repo2 "$SCRIPTS/board-register.sh" "second-repo ticket" enhancement P2 \
  --body-file "$SPEC10" 2>&1)" || {
    echo "FAIL $(basename "$0") — second-repo register failed: $OUT2" >&2; exit 1; }
TID2="$(printf '%s\n' "$OUT2" | awk 'END{print $1}')"
# The server's own attribution, read straight off the row — the credential here
# is unscoped, so before dp#33 this landed in the founding repo instead.
t "a register from the second checkout lands in the SECOND repo" "repo=[a2-second-repo]" \
  bash -c "curl -s -H 'authorization: Bearer $AUTOMATION_TOKEN' \
    '$BOARD_API_URL/tickets/$TID2' | python3 -c \"
import json, sys; print('repo=[%s]' % json.load(sys.stdin)['repo'])\""

# The read side, through the verb a human actually uses. Narrowed, each checkout
# sees its own board; widened, one service.
t  "and the second repo's list shows its own ticket" "#$TID2 " in_repo2 "$SCRIPTS/board-list.sh"
nt "but not the first repo's" "#$TID_L "                in_repo2 "$SCRIPTS/board-list.sh"
nt "and the first repo's list does not show the second's" "#$TID2 " \
  in_repo "$SCRIPTS/board-list.sh"
t  "--all-repos shows the first repo's ticket from the second checkout" "#$TID_L " \
  in_repo2 "$SCRIPTS/board-list.sh" --all-repos
t  "and the second's beside it"  "#$TID2 " in_repo2 "$SCRIPTS/board-list.sh" --all-repos
t  "saying so in the header"     "all repos" in_repo2 "$SCRIPTS/board-list.sh" --all-repos

# Every verb above went over the API. The gh CLI has no business on this path.
nt "the gh CLI is never invoked across the whole flow" "GH INVOKED" cat "$GH_LOG"

finish
