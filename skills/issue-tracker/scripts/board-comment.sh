#!/usr/bin/env bash
# board-comment.sh — append a comment-family event to a ticket, either binding.
#
# Usage:
#   board-comment.sh <number> <text>                       # plain comment
#   board-comment.sh <number> --kind <k> --json '<payload>' [--text <text>]
#     k: parent-impact | closure-package | parent-impact-consumed
#   board-comment.sh <number> -- <text>   # text that starts with a dash
#
# gh mode: `gh issue comment` (typed kinds land as "[<kind>] <json>" marker
# comments — the sweep's IMPACT scan reads that convention). API mode:
# POST /tickets/:id/comment — the only carrier for the E2 typed event ops.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="${1#\#}"; shift
kind="comment" text="" json="" have_text=0
# One unconditional loop: options are options wherever they sit, and the first
# bare token is the text. Anything else dies — every parse error here would
# otherwise land as a SUCCESSFUL board write carrying the wrong content.
while [ $# -gt 0 ]; do case "$1" in
  # `--` ends the options: comment text legitimately starts with a dash
  # ("--plan is void here"), and without an escape that text was refused as an
  # unknown option — with no way to say it at all.
  --) shift
      while [ $# -gt 0 ]; do
        [ "$have_text" -eq 0 ] || die "the comment text was given twice: $1"
        text="$1"; have_text=1; shift
      done ;;
  --kind) _need_arg "$1" "${2:-}"; kind="$2"; shift 2 ;;
  --json) _need_arg "$1" "${2:-}"; json="$2"; shift 2 ;;
  # LAST-WINS IS NOT A POLICY HERE. `--text a --text b`, or a bare token beside
  # a --text, silently posted one of them and dropped the other; a board write
  # carrying half of what the caller said is worse than a refusal.
  --text) _need_arg "$1" "${2:-}"
          [ "$have_text" -eq 0 ] || die "the comment text was given twice: --text $2"
          text="$2"; have_text=1; shift 2 ;;
  --*) die "unknown option: $1 (put -- ahead of comment text that starts with a dash)" ;;
  *) [ "$have_text" -eq 0 ] || die "the comment text was given twice: $1"
     text="$1"; have_text=1; shift ;;
esac; done
case "$kind" in
  comment|parent-impact|closure-package|parent-impact-consumed) ;;
  *) die "kind must be one of comment|parent-impact|closure-package|parent-impact-consumed" ;;
esac
# Validated once, ahead of the binding branch: gh mode interpolates the payload
# into a marker comment rather than parsing it, so without this the same
# malformed input would die in one binding and post in the other.
if [ -n "$json" ]; then
  _json_err="$(T_JSON="$json" python3 -c 'import json, os, sys
try:
    json.loads(os.environ["T_JSON"])
except ValueError as e:
    sys.exit(str(e))' 2>&1)" || die "--json is not valid JSON: $_json_err"
fi

if [ "$BOARD_BINDING" = api ]; then
  T_ID="$tid" T_KIND="$kind" T_TEXT="$text" T_JSON="$json" _api_py - <<'PY'
import json, os
import _board_api as A
env = os.environ
body = json.loads(env["T_JSON"]) if env["T_JSON"] else None
out = A.comment(env["T_ID"], kind=env["T_KIND"],
                text=env["T_TEXT"] or None, body=body)
print(out["eventId"])
PY
else
  if [ "$kind" = comment ]; then
    gh issue comment "$tid" -R "$BOARD_REPO" --body "$text"
  else
    gh issue comment "$tid" -R "$BOARD_REPO" --body "[$kind] ${text:+$text }${json}"
  fi
fi
_rerender_if_serving
