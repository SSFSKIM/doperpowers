#!/usr/bin/env bash
# board-register.sh — open a board ticket (a GitHub issue) with its edges typed.
#
# Usage:
#   board-register.sh <title> <category> [--state S] [--note TEXT] [--parent N]
#                     [--blocked-by N[,N...]] [--spawned-by N] [--body-file F]
#
#   category  bug | enhancement
#   --state   birth state: ready-for-agent (default) | needs-info | blocked | deferred
#             (needs-info / blocked require --note)
#   --parent / --blocked-by take issue numbers; edges are created as native
#   sub-issue / dependency relations. --spawned-by is provenance (board:meta).
#   --body-file seeds the issue body (else a pre-spec skeleton is used).
#
# Prints "<number> <url>" — then YOU flesh out the pre-spec body:
#   gh issue edit <number> --body-file <file>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
title="$1" category="$2"
shift 2
state="ready-for-agent" note="" parent="" blocked_by="" spawned_by="" body_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --state) _need_arg "$1" "${2:-}"; state="$2"; shift 2 ;;
    --note) _need_arg "$1" "${2:-}"; note="$2"; shift 2 ;;
    --parent) _need_arg "$1" "${2:-}"; parent="$2"; shift 2 ;;
    --blocked-by) _need_arg "$1" "${2:-}"; blocked_by="$2"; shift 2 ;;
    --spawned-by) _need_arg "$1" "${2:-}"; spawned_by="$2"; shift 2 ;;
    --body-file) _need_arg "$1" "${2:-}"; body_file="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -z "$body_file" ] || [ -f "$body_file" ] || die "no such file: $body_file"

T_TITLE="$title" T_CATEGORY="$category" T_STATE="$state" T_NOTE="$note" \
T_PARENT="$parent" T_BLOCKED="$blocked_by" T_SPAWNED="$spawned_by" \
T_BODY_FILE="$body_file" _py - <<'PY'
import os
import re
import _board as B

env = os.environ
# Titles are one line: collapse newlines/whitespace runs so a title can never
# spoof extra rows in line-oriented views (board-list).
title = " ".join(env["T_TITLE"].split())
category, state, note = env["T_CATEGORY"], env["T_STATE"], env["T_NOTE"]
if not title:
    B.die("title must be non-empty")
if category not in ("bug", "enhancement"):
    B.die("category must be bug|enhancement")
if state not in B.BIRTH:
    B.die("birth state must be one of: %s" % ", ".join(B.BIRTH))
if state in ("needs-info", "blocked") and not note:
    B.die("--note is required for state %s" % state)

tickets = B.snapshot()
parent = B.resolve(env["T_PARENT"], tickets) if env["T_PARENT"] else None
spawned = B.resolve(env["T_SPAWNED"], tickets) if env["T_SPAWNED"] else None
blocked = [B.resolve(b, tickets) for b in env["T_BLOCKED"].split(",") if b]

PRE_SPEC = """## Problem & intent

_(pre-spec: fill in)_

## Constraints

## Success criteria

## Open questions

## Decision log
"""
if env["T_BODY_FILE"]:
    with open(env["T_BODY_FILE"]) as f:
        body = f.read()
else:
    body = PRE_SPEC
meta = {}
if spawned:
    meta["spawned-by"] = "#%s" % spawned
if note:
    meta["note"] = note
body = B.render_body(body, meta)

B.ensure_status_labels()
out = B.gh(["issue", "create", "-R", B.repo(), "--title", title,
            "--label", "%s,%s%s" % (category, B.STATUS_PREFIX, state),
            "--body-file", "-"], input_text=body)
m = re.search(r"/issues/(\d+)\s*$", out.strip())
if not m:
    B.die("could not parse the created issue number from: %s" % out.strip())
num, url = m.group(1), out.strip().splitlines()[-1]

# The new issue's node (for edge mutations we need its GraphQL id).
node = {"id": B.graphql(
    """query($owner:String!,$name:String!,$n:Int!){
         repository(owner:$owner,name:$name){ issue(number:$n){ id } } }""",
    owner=B.repo().split("/")[0], name=B.repo().split("/")[1],
    n=int(num))["repository"]["issue"]["id"]}

if parent:
    B.add_sub_issue(tickets[parent], node)
for b in blocked:
    B.add_blocked_by(node, tickets[b])
if note:
    B.comment(num, "[board] %s: %s" % (state, note))

print("%s %s" % (num, url))
PY
