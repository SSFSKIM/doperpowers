#!/usr/bin/env bash
# board-register.sh — open a board ticket (a GitHub issue) with its edges typed.
#
# Usage:
#   board-register.sh <title> <category> <priority> [--state S] [--note TEXT]
#                     [--parent N] [--blocked-by N[,N...]] [--spawned-by N]
#                     [--body-file F]
#
#   category  bug | enhancement | spike (exploration lane: deliverable is a
#             findings comment, never a merge — see doperpowers:implementing)
#             | env-issue (environmental friction report — E2: defaults to
#             needs-human unless the registrar names an agent-executable
#             repair path via an explicit --state)
#   priority  P0 (drop everything) | P1 | P2 | P3 (someday) — required; becomes
#             the managed priority:* label (change later: board-priority.sh)
#   --state   birth state: ready-for-implementer (default) | ready-for-architect
#             | needs-human | needs-info | interactive-preferred | deferred
#             (the three park states require --note)
#   --parent / --blocked-by take issue numbers; edges are created as native
#   sub-issue / dependency relations. --spawned-by is provenance (board:meta).
#   --body-file seeds the issue body (else a pre-spec skeleton is used).
#
# A pre-spec skeleton is never implementable: explicit birth into a
# dispatchable lane state without a real body is refused, and a DEFAULT birth
# with the skeleton demotes to needs-info (with a spec-pending note). Fill the
# body, then board-transition.sh to its lane state — the transition re-checks
# the body.
#
# Prints "<number> <url>" — then YOU flesh out the pre-spec body:
#   gh issue edit <number> --body-file <file>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 3 ] || { usage_from_header "$0" >&2; exit 2; }
title="$1" category="$2" priority="$3"
shift 3
state="ready-for-implementer" state_explicit=0 note="" parent="" blocked_by="" spawned_by="" body_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --state) _need_arg "$1" "${2:-}"; state="$2"; state_explicit=1; shift 2 ;;
    --note) _need_arg "$1" "${2:-}"; note="$2"; shift 2 ;;
    --parent) _need_arg "$1" "${2:-}"; parent="$2"; shift 2 ;;
    --blocked-by) _need_arg "$1" "${2:-}"; blocked_by="$2"; shift 2 ;;
    --spawned-by) _need_arg "$1" "${2:-}"; spawned_by="$2"; shift 2 ;;
    --body-file) _need_arg "$1" "${2:-}"; body_file="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -z "$body_file" ] || [ -f "$body_file" ] || die "no such file: $body_file"

T_TITLE="$title" T_CATEGORY="$category" T_PRIORITY="$priority" T_STATE="$state" \
T_STATE_EXPLICIT="$state_explicit" \
T_NOTE="$note" T_PARENT="$parent" T_BLOCKED="$blocked_by" T_SPAWNED="$spawned_by" \
T_BODY_FILE="$body_file" _py - <<'PY'
import os
import re
import _board as B

env = os.environ
# Titles are one line: collapse newlines/whitespace runs so a title can never
# spoof extra rows in line-oriented views (board-list).
title = " ".join(env["T_TITLE"].split())
category, state, note = env["T_CATEGORY"], env["T_STATE"], env["T_NOTE"]
priority = env["T_PRIORITY"]
if not title:
    B.die("title must be non-empty")
if category not in B.CATEGORIES:
    B.die("category must be %s" % "|".join(B.CATEGORIES))
if priority not in B.PRIORITIES:
    B.die("priority must be one of %s" % "|".join(B.PRIORITIES))
if state not in B.BIRTH:
    B.die("birth state must be one of: %s" % ", ".join(B.BIRTH))
if state in B.NOTE_REQUIRED and not note:
    B.die("--note is required for state %s" % state)
# A spike has no legal exit from ready-for-architect: role resolution is
# state-free for spikes (category outranks lane — implement-dispatch.sh
# dispatches the spike protocol from EITHER lane queue), but the spike
# protocol's gate-pass write is `in-progress`, and
# LEGAL["ready-for-architect"] has no `in-progress` edge — a spike stranded
# there is left with only the parks, AND its stuck state eats an
# architect-lane slot (ARCHITECT_MAX_CONCURRENT counts by ticket state, not
# by which protocol actually dispatched). An earlier review declined a
# registration-time ban absent a reproduced failure; this failure is now
# reproduced, so the ban is earned.
if category == "spike" and state == "ready-for-architect":
    B.die("a spike cannot be born ready-for-architect — register it "
          "ready-for-implementer (the default); spikes dispatch on the "
          "spike protocol from either lane queue and have no legal exit "
          "from the architect queue")
# E2 birth rule (inverted for this category only): environmental friction
# that an authorized agent could reach would typically already be solved —
# unsure defaults to the human, not the implement queue. An explicit
# --state is the registrar's positive claim of a named repair path.
if category == "env-issue" and env["T_STATE_EXPLICIT"] != "1":
    state = "needs-human"
    if not note:
        B.die("an env-issue defaults to needs-human and requires --note "
              "naming the requested intervention (or pass an explicit "
              "--state with a named agent repair path)")

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

# A pre-spec skeleton is never implementable: born into a dispatchable lane
# state, it is dispatchable before any spec exists (observed live: ticket
# registered + auto-dispatched within 45 seconds, spec never written, the
# implementer decided the security contract itself). Explicit birth into a
# dispatchable lane state refuses a skeleton; the default demotes to needs-info.
if state in ("ready-for-architect", "ready-for-implementer") and "(pre-spec: fill in)" in body:
    if env["T_STATE_EXPLICIT"] == "1":
        B.die("a pre-spec skeleton cannot be born into a dispatchable lane state — pass "
              "--body-file with the spec, or birth it needs-info/needs-human")
    state = "needs-info"
    if not note:
        note = ("pre-spec skeleton — fill the body, then "
                "board-transition.sh to its lane state")
meta = {}
if spawned:
    meta["spawned-by"] = "#%s" % spawned
if note:
    meta["note"] = note
body = B.render_body(body, meta)

B.ensure_labels()
out = B.gh(["issue", "create", "-R", B.repo(), "--title", title,
            "--label", "%s,%s%s,%s%s" % (category, B.STATUS_PREFIX, state,
                                         B.PRIORITY_PREFIX, priority),
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

_rerender_if_serving
