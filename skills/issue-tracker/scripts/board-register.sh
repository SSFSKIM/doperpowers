#!/usr/bin/env bash
# board-register.sh — open a board ticket (a GitHub issue) with its edges typed.
#
# Usage:
#   board-register.sh <title> <category> <priority> [--state S] [--note TEXT]
#                     [--parent N] [--blocked-by N[,N...]] [--spawned-by N]
#                     [--body-file F] [--repair-path TEXT]
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
#   --repair-path names the agent-executable repair that licenses an env-issue
#   into an agent lane (API binding only — A1 requires it for that birth).
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
state="ready-for-implementer" state_explicit=0 note="" parent="" blocked_by="" spawned_by="" body_file="" repair_path=""
while [ $# -gt 0 ]; do
  case "$1" in
    --state) _need_arg "$1" "${2:-}"; state="$2"; state_explicit=1; shift 2 ;;
    --note) _need_arg "$1" "${2:-}"; note="$2"; shift 2 ;;
    --parent) _need_arg "$1" "${2:-}"; parent="$2"; shift 2 ;;
    --blocked-by) _need_arg "$1" "${2:-}"; blocked_by="$2"; shift 2 ;;
    --spawned-by) _need_arg "$1" "${2:-}"; spawned_by="$2"; shift 2 ;;
    --body-file) _need_arg "$1" "${2:-}"; body_file="$2"; shift 2 ;;
    --repair-path) _need_arg "$1" "${2:-}"; repair_path="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -z "$body_file" ] || [ -f "$body_file" ] || die "no such file: $body_file"
# The repair path is an A1 field: it is what licenses an environment failure
# into an agent lane there, and gh mode expresses that claim as an explicit
# --state alone. Refused rather than dropped — a documented invocation that
# silently loses its argument is worse than one that fails.
[ -z "$repair_path" ] || [ "$BOARD_BINDING" = api ] \
  || die "--repair-path is api-binding-only: in gh mode an explicit --state IS the named repair path"

# API mode: the server owns birth legality (the state machine, the pre-spec
# refusal, the env-issue inversion), so the client assembles the payload and
# reports what came back — none of the gh path's client-side adjudication runs.
if [ "$BOARD_BINDING" = api ]; then
  T_TITLE="$title" T_CATEGORY="$category" T_PRIORITY="$priority" T_STATE="$state" \
  T_STATE_EXPLICIT="$state_explicit" T_NOTE="$note" T_PARENT="$parent" \
  T_BLOCKED="$blocked_by" T_SPAWNED="$spawned_by" T_BODY_FILE="$body_file" \
  T_REPAIR="$repair_path" _api_py - <<'PY'
import contextlib
import io
import os
import sys
import _board_api as A
env = os.environ
title = " ".join(env["T_TITLE"].split())
CATEGORY_MAP = {"bug": "work", "enhancement": "work",
                "spike": "spike", "env-issue": "env-issue"}
if env["T_CATEGORY"] not in CATEGORY_MAP:
    A.die("category must be %s" % "|".join(CATEGORY_MAP))
body = open(env["T_BODY_FILE"]).read() if env["T_BODY_FILE"] else ""
note = env["T_NOTE"]
state = env["T_STATE"]
explicit = env["T_STATE_EXPLICIT"] == "1"
# No API note field for the birth question (arkho#7): the body head carries it.
# The condition is about which births can END UP parked, not which state was
# asked for. An IMPLICIT birth has no requested state at all — `state` here is
# only the shell's default — and the server decides: an env-issue inverts to
# needs-human (E2), a pre-spec skeleton demotes to needs-info. Both are park
# births by outcome, and gh mode makes the note MANDATORY on the first of them,
# so keying on the requested state discarded required human input. An EXPLICIT
# birth is the registrar naming the lane, and only the park states there make
# the note a question the body must carry.
PARK_BIRTHS = ("needs-human", "needs-info", "interactive-preferred")
# A PARK IS A QUESTION, and a question with no text is not one. gh mode makes
# the note mandatory for every park birth and for the implicit env-issue
# inversion; A1 falls back to the TITLE as the decision question when the body
# is empty, so the same call produced a park whose standing question was a
# ticket name. Enforced here because the server cannot tell the two apart.
if explicit and state in PARK_BIRTHS and not note and not body:
    A.die("--note is required for state %s — it is the question the park stands "
          "on (or pass --body-file, whose head A1 reads as that question)" % state)
if (not explicit and env["T_CATEGORY"] == "env-issue"
        and not note and not body and not env["T_REPAIR"]):
    A.die("an env-issue defaults to needs-human and requires --note naming the "
          "requested intervention (or an explicit --state with --repair-path "
          "naming an agent-executable repair)")
# A BODYLESS TICKET IS NEVER DISPATCHABLE. gh mode seeds a pre-spec skeleton
# when no --body-file is given, then refuses an EXPLICIT birth into a lane state
# and demotes the DEFAULT one to needs-info. A1 stores an empty body and
# defaults to ready-for-implementer, so the same call produced a dispatchable
# ticket with no statement of work — the parity claim's exact counterexample,
# and the failure gh mode's rule was written from (observed live: registered and
# auto-dispatched within 45 seconds, spec never written, the implementer decided
# the security contract itself).
#
# The RULING is mirrored; the skeleton is not. A1's body IS the assignment the
# claim hands the worker, and this client has no body-edit route (arkho#7) — so
# seeding a skeleton would ship an assignment nobody can fill and, worse, make
# the park question the skeleton's own text. An EXPLICITLY EMPTY --body-file is
# the registrar saying so, exactly as in gh mode, and is left alone.
if not body and not env["T_BODY_FILE"]:
    if explicit and state in ("ready-for-architect", "ready-for-implementer"):
        A.die("a ticket with no body cannot be born into a dispatchable lane "
              "state — pass --body-file with the spec, or birth it "
              "needs-info/needs-human")
    if not explicit and env["T_CATEGORY"] != "env-issue":
        # The implicit default is the implementer queue, and nothing enters it
        # without a statement of work. env-issue keeps its own inverted default
        # (needs-human), which is a park rather than a lane.
        state = "needs-info"
        explicit = True
        if not note:
            note = ("registered with no body — re-register with --body-file once "
                    "the spec exists, then board-transition.sh to its lane state")
if note and (not explicit or state in PARK_BIRTHS):
    body = note + ("\n\n" + body if body else "")


def ref(raw):
    """A ticket ref for an edge — '#42'/'42' → 42, same refusal as gh mode."""
    n = raw.lstrip("#")
    if not n.isdigit():
        A.die("not an issue number: %s" % raw)
    return int(n)


payload = {"title": title, "category": CATEGORY_MAP[env["T_CATEGORY"]],
           "priority": env["T_PRIORITY"]}
if explicit:
    payload["birth"] = state
if body:
    payload["body"] = body
if env["T_REPAIR"]:
    payload["repairPath"] = env["T_REPAIR"]
if env["T_PARENT"]:
    payload["parent"] = ref(env["T_PARENT"])
if env["T_SPAWNED"]:
    payload["spawnedBy"] = ref(env["T_SPAWNED"])
if env["T_BLOCKED"]:
    payload["blockedBy"] = [ref(b) for b in env["T_BLOCKED"].split(",") if b]
# The pointer below is a claim about CANON, so it may only ride the server
# saying so. Every refusal and every outage leaves the same local shape — a
# SystemExit out of the client — and the identifier lives in the message the
# client already printed, so capture that stream and re-emit it verbatim.
err = io.StringIO()
try:
    with contextlib.redirect_stderr(err):
        out = A.register(payload)
except BaseException:
    sys.stderr.write(err.getvalue())
    sys.stderr.flush()
    # A spike birth into ready-for-architect is a known canon divergence — but
    # only when the server actually refused it as one. A 500, an auth reject or
    # a dead socket is an outage, and blaming divergence for it sends the reader
    # to the wrong ticket.
    if ("illegal-birth" in err.getvalue()
            and env["T_CATEGORY"] == "spike" and state == "ready-for-architect"):
        print("note: design-first spikes are gh-only until the arkho#7 ruling "
              "(https://github.com/SSFSKIM/arkho/issues/7)", flush=True)
    raise
sys.stderr.write(err.getvalue())
print("%s %s/tickets/%s" % (out["id"], os.environ["BOARD_API_URL"], out["id"]))
PY
  _rerender_if_serving
  exit 0
fi

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
# (A spike born ready-for-architect used to be refused here: role resolution
# was category-first, so the spike protocol dispatched from either lane queue
# and its gate-pass write — `in-progress` — had no LEGAL edge from the
# architect queue. implement-dispatch.sh now routes that queue on STATE, so
# such a ticket gets an ARCHITECT whose exit is `in-design`. A design-first
# spike is a supported route and the ban is gone.)
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
