#!/usr/bin/env bash
# board-body.sh — rewrite a ticket's statement of work.
#
# Usage:
#   board-body.sh <number> --body-file F     (F may be - for stdin; an empty
#                                             file is a legal edit — clearing
#                                             the statement of work)
#
# API mode posts the whole text to POST /tickets/:id/body. The server refuses
# `ticket-owned` while a run holds the ticket: the body IS the claim-time
# assignment, so an edit under an open run reaches nobody — for a bound park
# the enrichment channel is the park ANSWER, never the body. A no-change
# rewrite answers (noop).
#
# gh mode is a meta-preserving read-modify-write: the prose is replaced and
# the trailing `board:meta` block is spliced back BYTE-FOR-BYTE — never
# parsed, never re-rendered — so unknown keys, comments and noncanonical
# spacing survive an older client. This is the safe counterpart to editing
# the body with bare `gh issue edit`, which clobbers the block.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -eq 3 ] && [ "$2" = --body-file ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" body_file="$3"
if [ "$body_file" = - ]; then
  body_file="$(mktemp)"
  cat > "$body_file"
else
  [ -f "$body_file" ] || die "no such file: $body_file"
fi

if [ "$BOARD_BINDING" = api ]; then
  T_ID="$tid" T_FILE="$body_file" _api_py - <<'PY'
import os
import _board_api as A

tid = A.ref(os.environ["T_ID"])
out = A.set_body(tid, open(os.environ["T_FILE"]).read())
print("#%s: body rewritten%s" % (tid, " (noop)" if out.get("noop") else ""))
PY
  _rerender_if_serving
  exit 0
fi

T_ID="$tid" T_FILE="$body_file" _py - <<'PY'
import os
import _board as B

env = os.environ
tid = B.resolve(env["T_ID"])
# One issue read, NOT B.snapshot(): the verb needs a single body, and the
# snapshot's paginated GraphQL sweep is overhead a body edit has no business
# paying (nor could a caller stub it).
old = B.gh(["issue", "view", tid, "-R", B.repo(), "--json", "body",
            "--jq", ".body"])
new = open(env["T_FILE"]).read()

# The raw splice. META_RE is consulted for a byte OFFSET only — the matched
# text is carried through untouched, never parsed and never re-rendered, so
# unknown keys, comment lines and noncanonical spacing all survive a client
# older than whatever wrote them.
#
# The block that counts is the LAST one. META_RE is leftmost-first and its
# `.*?` will happily span from a marker-like example QUOTED in the prose all
# the way to the real trailing `-->`, so splicing at the first match would
# carry the prose this edit was told to replace. Walk to the rightmost match.
m = None
pos = 0
while True:
    nxt = B.META_RE.search(old, pos)
    if not nxt:
        break
    m, pos = nxt, nxt.start() + 1
if m:
    # Only the newlines AROUND the block are normalized (to render_body's
    # blank-line-then-block shape); its own bytes are untouched.
    new = "%s\n\n%s\n" % (new.rstrip("\n"), old[m.start():].strip("\n"))

B.set_body(tid, new)
print("#%s: body rewritten" % tid)
PY

_rerender_if_serving
