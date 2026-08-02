#!/usr/bin/env bash
# board-transition.sh — move a ticket to a new state, enforcing the invariants.
#
# Usage:
#   board-transition.sh <number> <to-state> [note] [--branch NAME] [--pr URL] [--plan PATH@SHA|pre-spec]
#
# Enforces transition legality and mandatory notes (the park trio + wontfix),
# records branch/pr (board:meta), posts notes as [board] comments, and sweeps:
#   → ACTIVE      : entering in-design / in-progress / in-review from a
#                   NON-active state makes this the epic's first active
#                   child, and it pulls its parent epic(s) in-flight
#                   (architect queue → in-design; implementer queue or a
#                   needs-info release → in-progress) — PRE_PARK/PULL_FROM.
#                   needs-human / interactive-preferred / deferred parents are
#                   left alone: those parks own a session or the human.
#   → done/wontfix: an epic whose children are all terminal RETURNS to
#                   ready-for-architect for recomposition (E2) — epics are
#                   closed by an Architect's verdict, never by bookkeeping
#
# Repair path: an issue whose labels are off-machine (zero or 2+ status:*
# labels — lint calls these untracked/conflict) may transition to any OPEN
# state; the write normalizes the label set.
#
# Finalize path: re-running `<n> done` (or wontfix) on an ALREADY-terminal
# issue is not an error — it finalizes a ticket that closed outside the
# machine (a PR's "Closes #N" auto-close): strips residual status labels and
# runs the terminal sweeps. Idempotent.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" to="$2"
shift 2
note="" branch="" pr="" plan=""
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then note="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) _need_arg "$1" "${2:-}"; branch="$2"; shift 2 ;;
    --pr) _need_arg "$1" "${2:-}"; pr="$2"; shift 2 ;;
    --plan) _need_arg "$1" "${2:-}"; plan="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" T_PLAN="$plan" _py - <<'PY'
import json as _json_
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
to, note = env["T_TO"], env["T_NOTE"]
n = tickets[tid]
cur = n["state"]

if to not in B.STATES:
    B.die("unknown state: %s" % to)
# Same ban as board-register.sh (Finding A): a LEAF spike has no legal exit
# from ready-for-architect (LEGAL["ready-for-architect"] has no
# in-progress edge, and the spike protocol's gate-pass write IS
# in-progress regardless of which lane queue dispatched it). Close every
# entry into the state, not just the birth one.
#
# Leaf-hood is the discriminant, not the label. A spike that DECOMPOSED is
# an epic, and an epic in ready-for-architect is a recomposition or
# reconciliation claim dispatched to an ARCHITECT — the dispatcher routes it
# that way on epic-hood, over its category — so the spike protocol and its
# in-progress write never enter the picture. Banning the edge by category
# alone rejected such an epic's scale-defect route (in-review →
# ready-for-architect) and left the parent mislabeled in-review with nothing
# able to move it.
if to == "ready-for-architect" and n["category"] == "spike" \
   and tid not in B.epics(tickets):
    B.die("#%s is a leaf spike — it has no legal exit from "
          "ready-for-architect; it stays in its current lane" % tid)
# E2 epic guard: the in-design → done / in-review edges exist ONLY for a
# RECOMPOSITION claim (the scoped terminal-authority exception) — an epic
# whose children are all terminal. A leaf Architect never closes or reviews
# its own ticket, and an epic held on a RECONCILIATION claim (children still
# running) exits in-design by releasing to needs-info, never by a verdict:
# closing there would skip recomposition verification entirely.
if cur == "in-design" and to in ("done", "in-review"):
    if tid not in B.epics(tickets):
        B.die("in-design → %s is the epic recomposition edge — #%s has no "
              "children; a leaf exits in-design via ready-for-implementer "
              "or a park" % (to, tid))
    if not B.recomposition_ready(tickets, tid):
        B.die("#%s still has non-terminal children — the in-design → %s "
              "verdict edges belong to recomposition (every child terminal). "
              "A reconciliation claim releases the epic instead: needs-info "
              "\"reconciled: ... — waiting on children\"" % (tid, to))
if to == cur:
    if cur not in B.TERMINAL:
        B.die("#%s is already %s" % (tid, cur))
    # Finalize: the issue reached this terminal state outside the machine
    # (e.g. a merged PR's "Closes #N" auto-close), so the label strip and the
    # terminal sweeps never ran. Run them now; safe to re-run.
    lines = []
    if n["status_labels"]:
        B.edit_labels(tid, remove=[B.STATUS_PREFIX + s for s in n["status_labels"]])
        n["status_labels"] = []
        lines.append("#%s: %s — stripped residual status labels" % (tid, cur))
    if note:
        B.comment(tid, "[board] %s: %s" % (to, note))
    B.recompose_epics(tickets, n.get("parent"), lines)
    out = (B.newly_eligible(tickets, tid) if to == "done" else []) + lines
    for ln in out:
        print(ln)
    if not out:
        print("#%s: already %s — nothing to finalize" % (tid, cur))
    raise SystemExit(0)
if cur in (B.UNTRACKED, B.CONFLICT):
    # repair: any open state is reachable; terminal still goes through the machine
    if to in B.TERMINAL:
        B.die("#%s is %s — repair it to an open state first (it has %d status labels)"
              % (tid, cur, len(n["status_labels"])))
elif to not in B.LEGAL[cur]:
    B.die("illegal transition: %s → %s (#%s)" % (cur, to, tid))

if (cur, to) in B.EDGE_NOTE_REQUIRED and not note:
    B.die("a note is required on the %s → %s edge" % (cur, to))

if (cur, to) in B.CONVERGENCE_EDGES:
    # Convergence rule (E1 transition 6): count prior traversals of THIS
    # edge since the last RESET comment; a second traversal converts to a
    # needs-human park. Comments are not in the snapshot — one extra gh
    # call, only on escalation edges.
    #
    # Two comments reset the count. [answers] is the human sanctioning
    # another go. [board-epic] ready-for-architect: is the board opening a
    # fresh Architect cycle on an EPIC — the recomposition-due return (new
    # children landed) and the reconciliation-due return (a new
    # [parent-impact] proposal) both do it. Without this, two successive
    # closure packages that each turn up a real defect read as one
    # mechanical bounce, and the second escalation — about a package that
    # did not exist during the first — is rewritten into a needs-human park.
    # The prefix is written only by epic bookkeeping (apply_state's
    # bookkeeping branch), so it never appears on a leaf.
    #
    # This count is comment-CONTROLLED board behavior, same class as the
    # sweep's IMPACT scans: on a public consumer repo an outsider could
    # pre-seed an edge marker (forcing the next legitimate traversal into a
    # needs-human park) or post [answers] (buying unbounded bounces). So only
    # repo-side authors count or reset — every board and worker write is the
    # token identity, i.e. OWNER. A comment that is not an object carries no
    # association at all and is therefore untrusted.
    import json as _json
    TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
    comments = _json.loads(B.gh(["issue", "view", tid, "-R", B.repo(),
                                 "--json", "comments"])).get("comments") or []
    marker = "[board] %s → %s:" % (cur, to)
    count = 0
    for c in comments:
        if not isinstance(c, dict) or (c.get("authorAssociation") or "") not in TRUSTED:
            continue
        body = (c.get("body") or "").lstrip()
        if body.startswith("[answers]"):
            count = 0
        elif body.startswith("[board-epic] ready-for-architect:"):
            count = 0
        elif body.startswith(marker):
            count += 1
    if count >= 1:
        note = ("convergence: second traversal of %s → %s — no third "
                "mechanical bounce; this traversal's position: %s — see "
                "the comment trail for the first" % (cur, to, note))
        to = "needs-human"

if to in B.NOTE_REQUIRED and not note:
    B.die("a note is required when moving to %s" % to)
if to == "in-review" and not env["T_PR"]:
    # A RETURN to in-review (the pre-park: meta — E1 transition 7) never
    # re-supplies --pr: the ticket's board:meta already carries the artifact
    # from the entry the park interrupted. The invariant is "a ticket in
    # in-review always has a PR recorded", not "every entry carries the
    # flag". For an EPIC the pr slot carries the recomposition closure
    # package (E2) — same invariant, different artifact.
    #
    # But ONLY that return may ride the recorded value. A stale pr: survives
    # every route back out of in-review (a review that bounced the ticket to
    # ready-for-architect leaves it; only recomposition clears it, and the
    # reconciliation return deliberately does not), so accepting the meta on
    # any entry pointed the board at a superseded PR — or, on an epic, at the
    # previous cycle's closure package — with nobody having said so.
    prepark = B.parse_meta(n.get("body")).get("pre-park")
    if not (cur in B.PARKED and prepark == "in-review" and n.get("pr")):
        B.die("a PR link is required when moving to in-review (--pr URL; for an "
              "epic: the closure-package URL). Only a park return whose "
              "pre-park: meta records in-review may reuse the recorded one.")
if env["T_PLAN"]:
    import re as _re
    # The EDGE, not just the destination: a plan pin authorizes gate-free
    # PLAN-EXECUTION, and only an Architect finishing a design pass may mint
    # one. Every other legal promotion into ready-for-implementer (a park
    # return from needs-info/needs-human/interactive-preferred/deferred)
    # would otherwise mint one too — and there is no legitimate re-supply
    # case, since plan meta survives park round-trips untouched.
    if cur != "in-design" or to != "ready-for-implementer":
        B.die("--plan rides the Architect handoff edge (in-design → "
              "ready-for-implementer) only")
    if env["T_PLAN"] != "pre-spec":
        if not _re.match(r"^\S+@[0-9a-f]{40}$", env["T_PLAN"]):
            B.die("--plan must be <repo-path>@<full-40-hex-sha> (an immutable pin) or the literal pre-spec")
        # A real pin authorizes gate-free PLAN-EXECUTION, and the worker that
        # executes it starts from a fresh cattle clone: without a recorded ref
        # the sha is reachable from, there is nothing to fetch and the pin
        # cannot serve the reclaim contract it exists for. `pre-spec` is
        # exempt — it names no revision, the issue body IS the plan.
        pin_branch = env["T_BRANCH"] or n.get("branch")
        if not pin_branch:
            B.die("a pinned plan needs a recorded branch the sha is reachable "
                  "from; pass --branch (the default branch is fine if the plan "
                  "landed there)")
        # ...and "recorded" is not "fetchable". A mistyped or unpushed sha, or
        # one whose tree lacks the named path, still minted gate-free
        # PLAN-EXECUTION against an artifact no cattle clone can fetch — the
        # worker would discover it only after the gate was already skipped.
        # Verify against the remote before writing any state, and fail CLOSED
        # on a verification failure AND on an API error: an unverifiable pin
        # is not a pin. The Architect pushes and retries.
        import subprocess as _sp
        pin_path, pin_sha = env["T_PLAN"].rsplit("@", 1)

        def _api(path):
            r = _sp.run(["gh", "api", path], capture_output=True, text=True)
            return r.returncode, r.stdout, r.stderr.strip()

        rc, out, err = _api("repos/%s/compare/%s...%s" % (B.repo(), pin_branch, pin_sha))
        if rc != 0:
            B.die("cannot verify the plan pin against branch %s: %s\n"
                  "  the pin is refused until it verifies — push the branch "
                  "(and the commit) and retry" % (pin_branch, err or "gh api failed"))
        try:
            status = (_json_.loads(out) or {}).get("status") or ""
        except ValueError:
            status = ""
        if status not in ("identical", "behind"):
            B.die("plan sha %s is not on branch %s (compare says %s) — a "
                  "PLAN-EXECUTION worker fetches the sha from that branch and "
                  "would find nothing; push the commit to it and retry"
                  % (pin_sha[:12], pin_branch, status or "nothing"))
        rc, _out, err = _api("repos/%s/contents/%s?ref=%s" % (B.repo(), pin_path, pin_sha))
        if rc != 0:
            B.die("the plan path %s does not exist at %s (%s) — the pin names "
                  "an artifact the worker cannot read; fix the path or the sha "
                  "and retry" % (pin_path, pin_sha[:12], err or "gh api failed"))
if to in B.DISPATCHABLE and "(pre-spec: fill in)" in (n.get("body") or ""):
    B.die("#%s is still a pre-spec skeleton — fill the body (gh issue edit "
          "%s --body-file <spec>) before a dispatchable lane state" % (tid, tid))

B.ensure_labels()
extra = {}
if env["T_BRANCH"]:
    extra["branch"] = env["T_BRANCH"]
if env["T_PR"]:
    extra["pr"] = env["T_PR"]
if env["T_PLAN"]:
    extra["plan"] = env["T_PLAN"]
elif to == "ready-for-architect" or (cur == "in-design" and to == "ready-for-implementer"):
    # The plan: pin is void by definition on these two edges — clear it so
    # a superseded pin can never survive into gate-free PLAN-EXECUTION
    # (a real pin authorizes gate-free execution; conflating it with the
    # unrelated `pre-spec` ruling value caused two defects on this branch,
    # so this clears the field outright rather than keying on "has a pin").
    # Entry into ready-for-architect always means the plan is being
    # re-cut (T_PLAN can only be set on the in-design →
    # ready-for-implementer edge — validated above — so this branch never
    # collides with a fresh pin write). The Architect's own decompose exit
    # (in-design -> ready-for-implementer with no --plan) is a positive
    # "no plan" statement — a pin surviving it is stale by construction.
    # Deliberately NOT extended to other edges into ready-for-implementer:
    # a human unparking from needs-human should not silently void a
    # still-valid plan.
    extra["plan"] = None
if to == "needs-human" and cur in B.PRE_PARK:
    extra["pre-park"] = B.PRE_PARK[cur]
if cur == "needs-human" and to != "needs-human":
    extra["pre-park"] = None
lines = [B.apply_state(tickets, tid, to, note, extra_meta=extra)]

# Sweep: first active child pulls its epic chain to each parent's own
# in-flight state (PRE_PARK: architect queue → in-design, else in-progress).
# Any entry INTO an active state counts — an architect-lane child entering
# in-design is its epic's first active child exactly as an implementer-lane
# child entering in-progress is. The from-non-ACTIVE half is what keeps it
# to entries: in-review is only ever reached from an active state, so it
# never re-fires, and a child moving in-design → in-progress does not either.
if to in B.ACTIVE and cur not in B.ACTIVE:
    B.pull_epics(tickets, tid, lines)

# Sweep: a terminal child may return its epic for recomposition.
if to in B.TERMINAL:
    B.recompose_epics(tickets, n.get("parent"), lines)

# Report dependents this `done` made eligible (derived, nothing written).
eligible_lines = B.newly_eligible(tickets, tid) if to == "done" else []

for ln in eligible_lines + lines:
    print(ln)
PY


_rerender_if_serving
