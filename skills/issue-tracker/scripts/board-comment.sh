#!/usr/bin/env bash
# board-comment.sh — append a comment-family event to a ticket, either binding.
#
# Usage:
#   board-comment.sh <number> <text>                       # plain comment
#   board-comment.sh <number> --kind <k> --json '<payload>' [--text <text>]
#     k: parent-impact | closure-package | parent-impact-consumed
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
kind="comment" text="" json=""
if [ "${1:-}" != "--kind" ]; then text="$1"; shift
else
  while [ $# -gt 0 ]; do case "$1" in
    --kind) _need_arg "$1" "${2:-}"; kind="$2"; shift 2 ;;
    --json) _need_arg "$1" "${2:-}"; json="$2"; shift 2 ;;
    --text) _need_arg "$1" "${2:-}"; text="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac; done
fi
case "$kind" in
  comment|parent-impact|closure-package|parent-impact-consumed) ;;
  *) die "kind must be one of comment|parent-impact|closure-package|parent-impact-consumed" ;;
esac

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
