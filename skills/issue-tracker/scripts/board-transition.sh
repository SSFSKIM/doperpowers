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
#                   (architect queue → in-design; executor queue or a
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

# THE REGISTRY FENCES THE STATE MACHINE (dp#63). A ticket bound to a live
# worker mid-turn belongs to that worker: with 'already in-progress' as the
# only conflict signal, an orchestrator two-hop-closed a ticket a dispatched
# worker was completing, and both sessions shipped independent solutions
# (ida#1584). The liveness predicate is board-bind's live-owner rule (host +
# boot survival); the owner is recognized by its session id — every worker is
# a claude-harness session, so CLAUDE_CODE_SESSION_ID matches the meta's
# uuid/current across resumes. Deliberate exceptions state their reason in
# BOARD_OWNER_OVERRIDE (the sweep's recovery-cap park on a live-but-stalled
# worker rides it) and are acknowledged on stdout. Adjudication is LOCAL by
# construction, like the rule it reuses: a binding on another machine is
# invisible here. Runs ahead of the mode fork — the API server adjudicates
# RUNS via fences, but this client-side fence is what stands between a
# non-run session and a ticket a local worker owns, in either binding.
#
# Two scope cuts keep the fence honest. (1) Ticket numbers are BOARD-local
# and the registry is machine-global, so a binding only counts when its
# board-bind-stamped `board` key names THIS board; a meta predating the stamp
# fences anyway — bindings live hours, the ambiguity ages out. (2) A ticket
# already CLOSED on GitHub is past preventing: the fence exists to stop a
# second completion, and for a closed ticket that write is finalization
# bookkeeping (label strip + terminal sweeps) that refusing only delays —
# lingering `working` metas on merge-auto-closed tickets are routine
# (--no-wait workers finalize on the dispatcher's cadence, not the merge's).
# The probe runs only on the would-refuse path, gh mode only (API tickets
# close through the server, never outside the machine).
#
# The scan is deliberately UNLOCKED: a bind publishing concurrently with this
# read can slip a fresh owner in behind a transition already past the fence.
# Closing that window would mean holding the registry metalock across the
# transition's own gh/API calls — seconds of machine-wide bind starvation
# against a millisecond race — and gh mode has no arbiter that could give the
# pair a total order anyway. The fence's job is the HOURS-scale divergence
# (two sessions completing one ticket), not linearization.
if [ "$BOARD_BINDING" = api ]; then _fence_board="api:$BOARD_API_URL"
else _fence_board="gh:$BOARD_REPO"; fi
T_ID="$tid" T_DHOME="$DAEMON_HOME" T_SELF="${CLAUDE_CODE_SESSION_ID:-}" \
T_DSELF="${DAEMON_SELF_UUID:-}" \
T_OVR="${BOARD_OWNER_OVERRIDE:-}" T_BOARD="$_fence_board" python3 - <<'PY'
import glob
import json
import os
import re
import socket
import sys

env = os.environ
tid = env["T_ID"].lstrip("#")
if tid:
    def cur_boot():
        try:
            with open("/proc/sys/kernel/random/boot_id") as f:
                return f.read().strip()
        except OSError:
            out = os.popen("sysctl -n kern.boottime 2>/dev/null").read()
            m = re.search(r"sec = (\d+)", out)
            return m.group(1) if m else ""

    HOST, BOOT = socket.gethostname(), cur_boot()

    # Board keys compare NORMALIZED: _board_api.url() strips a trailing
    # slash before use, so "api:http://x/" and "api:http://x" name one
    # board — a raw compare would let a slash unfence a live owner.
    def _board_key(b):
        return "api:" + b[4:].rstrip("/") if b.startswith("api:") else b

    for path in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
        if path.endswith(".reply.json"):
            continue
        try:
            meta = json.load(open(path))
        except Exception:
            continue
        if str(meta.get("ticket", "")).lstrip("#") != tid:
            continue
        if meta.get("board") and _board_key(meta["board"]) != _board_key(env["T_BOARD"]):
            continue   # another board's #N — the number collision, not an owner
        if meta.get("status") not in ("working", "blocked"):
            continue   # only a MID-TURN owner fences; parked/idle owners are
                       # board-answer's and the dispatchers' business
        mh, mb = str(meta.get("host") or ""), str(meta.get("boot_id") or "")
        if (mh and mh != HOST) or (mb and BOOT and mb != BOOT):
            continue   # another boot: a worker that died without finalizing
        owner = str(meta.get("uuid") or os.path.basename(path)[:-5])
        if env["T_SELF"] and env["T_SELF"] in (owner, str(meta.get("current") or "")):
            break      # the binding owner moves its own ticket
        if env["T_DSELF"] and env["T_DSELF"] == owner:
            break      # a legacy codex-CLI turn: no harness session id, so
                       # codex-resume hands it its daemon uuid explicitly
        if env["T_OVR"]:
            print("override: #%s is mid-turn under %s (status=%s) — proceeding: %s"
                  % (tid, meta.get("name") or owner, meta.get("status"), env["T_OVR"]))
            break
        if env.get("BOARD_BINDING") == "gh":
            import subprocess
            r = subprocess.run(["gh", "issue", "view", tid, "-R",
                                env.get("BOARD_REPO", ""), "--json", "state"],
                               capture_output=True, text=True)
            try:
                closed = r.returncode == 0 and \
                    json.loads(r.stdout).get("state") == "CLOSED"
            except ValueError:
                closed = False   # an unreadable probe fails CLOSED — refuse below
            if closed:
                break
        sys.stderr.write(
            "error: #%s is mid-turn under live worker %s (%s, status=%s) — a "
            "transition by anyone but the binding owner completes work that "
            "worker already owns (dp#63). Let it finish or resume it "
            "(daemon-list.sh / daemon-resume.sh), retire the binding first "
            "(daemon-retire.sh %s), or overrule with a stated reason: "
            "BOARD_OWNER_OVERRIDE=\"<why>\" board-transition.sh ...\n"
            % (tid, meta.get("name") or owner, owner, meta.get("status"), owner))
        sys.exit(1)
PY

# API mode: legality, the convergence rule, the note/PR/plan requirements and
# every sweep above live server-side — the client sends the edge and reports
# the state the server wrote.
if [ "$BOARD_BINDING" = api ]; then
  # A PLAN PIN IS A GATE, NOT A FIELD. It authorizes gate-free PLAN-EXECUTION,
  # and A1 stores whatever primitive arrives on whatever legal edge — so on this
  # side the CLIENT is the only fence there is. "Thin client" was never a licence
  # to drop a gate the other binding enforces: transcript parity cuts both ways,
  # and an arbitrary --plan value here bought a worker the right to skip its gate
  # entirely. gh mode's four checks, mirrored:
  if [ -n "$plan" ]; then
    # 1. THE EDGE, not just the destination. Only an Architect finishing a
    #    design pass may mint a pin; every other legal promotion into
    #    ready-for-implementer (a park return) would otherwise mint one too, and
    #    there is no legitimate re-supply case — plan meta survives park
    #    round-trips untouched.
    _cur="$(T_ID="$tid" _api_py - <<'PY'
import os
import _board_api as A
# The one board read on this path that keeps the HUMAN default principal: the
# gate reads as whoever is transitioning, not as the fleet. A 404 prints empty
# exactly as the first-match miss of the whole-board scan did, and the shell
# turns that into the refusal below — what changed is that the emptiness is
# now authoritative. (No apostrophes in this heredoc: it lives inside a command
# substitution, where bash 3.2 lexes the body and a lone quote breaks the whole
# script at parse time.)
row = A.ticket(A.ref(os.environ["T_ID"]))
print(row["state"] if row else "")
PY
)" || die "--plan needs the ticket's current state to check the handoff edge, and the board would not answer"
    [ -n "$_cur" ] || die "--plan: #$tid does not exist on this board — the handoff edge cannot be checked"
    { [ "$_cur" = in-design ] && [ "$to" = ready-for-implementer ]; } \
      || die "--plan rides the Architect handoff edge (in-design → ready-for-implementer) only (#$tid is $_cur → $to)"
    if [ "$plan" != pre-spec ]; then
      # 2. An IMMUTABLE pin: a path and a full 40-hex sha, never a branch name
      #    or a short sha that can move under the worker.
      [[ "$plan" =~ ^[^[:space:]]+@[0-9a-f]{40}$ ]] \
        || die "--plan must be <repo-path>@<full-40-hex-sha> (an immutable pin) or the literal pre-spec"
      # 3. A RECORDED BRANCH the sha is reachable from. A PLAN-EXECUTION worker
      #    starts from a fresh cattle clone: without one there is nothing to
      #    fetch and the pin cannot serve the reclaim contract it exists for.
      #    A1's ticket projection carries no branch column, so unlike gh mode
      #    there is no recorded value to fall back on — --branch is required.
      [ -n "$branch" ] \
        || die "a pinned plan needs a branch the sha is reachable from; pass --branch (the API board records none to fall back on)"
      # 4. ...and "recorded" is not "fetchable". gh mode asks GitHub; there is no
      #    gh here, so the same question is put to the local checkout — which is
      #    the Architect's own, the one that just pushed the plan. Fail CLOSED on
      #    anything unverifiable: an unverifiable pin is not a pin.
      _sha="${plan##*@}" _path="${plan%@*}" _ref=""
      for _cand in "origin/$branch" "$branch"; do
        git -C "$BOARD_ROOT" rev-parse --verify --quiet "$_cand^{commit}" >/dev/null && { _ref="$_cand"; break; }
      done
      [ -n "$_ref" ] || die "branch $branch names no commit in this checkout — fetch it, then retry (the pin is refused until it verifies)"
      git -C "$BOARD_ROOT" merge-base --is-ancestor "$_sha" "$_ref" 2>/dev/null \
        || die "plan sha ${_sha:0:12} is not on branch $branch — a PLAN-EXECUTION worker fetches the sha from that branch and would find nothing; push the commit to it and retry"
      git -C "$BOARD_ROOT" cat-file -e "$_sha:$_path" 2>/dev/null \
        || die "the plan path $_path does not exist at ${_sha:0:12} — the pin names an artifact the worker cannot read; fix the path or the sha and retry"
    fi
  fi
  T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" T_PLAN="$plan" _api_py - <<'PY'
import os
import _board_api as A
env = os.environ
tid = A.ref(env["T_ID"])   # '#12' → 12, and a junk ref dies as a junk
                           # ref — not as A.transition's int() traceback
fence = os.environ.get("BOARD_RUN_FENCE") or None
out = A.transition(tid, env["T_TO"],
                   note=env["T_NOTE"] or None, pr=env["T_PR"] or None,
                   plan=env["T_PLAN"] or None, branch=env["T_BRANCH"] or None,
                   fence=int(fence) if fence else None)
# Print the state the server WROTE — convergence can transmute the target.
suffix = " (converged)" if out.get("converged") else ""
print("#%s: → %s%s" % (tid, out["to"], suffix))
PY
  _rerender_if_serving
  exit 0
fi

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
# (Every entry into ready-for-architect used to be closed to a LEAF spike,
# mirroring board-register.sh's birth ban — the spike protocol's gate-pass
# write is `in-progress`, which LEGAL["ready-for-architect"] does not have.
# Dispatch routes that queue on STATE now, so a spike there gets an ARCHITECT
# and exits via `in-design`; the ban is gone from both scripts.)
# E2 epic guard: the in-design → done / in-review edges exist ONLY for a
# RECOMPOSITION claim (the scoped terminal-authority exception) — an epic
# whose children are all terminal. A leaf Architect never closes or reviews
# its own ticket, and an epic held on a RECONCILIATION claim (children still
# running) exits in-design by releasing to needs-info, never by a verdict:
# closing there would skip recomposition verification entirely.
#
# `wontfix` joins done/in-review on the EPIC side only. LEGAL["in-design"]
# has it, and it closes the issue through the same apply_state, so an epic
# could be abandoned with children still running — every recomposition
# invariant bypassed by picking the third terminal instead of the first two.
# The leaf side of `wontfix` is deliberately NOT adjudicated here: whatever
# legality a leaf wontfix from in-design has today, it keeps.
if cur == "in-design" and to in ("done", "in-review", "wontfix"):
    is_epic = tid in B.epics(tickets)
    if to != "wontfix" and not is_epic:
        B.die("in-design → %s is the epic recomposition edge — #%s has no "
              "children; a leaf exits in-design via ready-for-implementer "
              "or a park" % (to, tid))
    if is_epic and not B.recomposition_ready(tickets, tid):
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
    TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
    comments = B.comments(tid)          # fully paginated: a page-1 read would
                                        # miss traversals and under-count
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
# THE META WRITE IS VALIDATED AHEAD OF EVERY LABEL WRITE ON THIS PATH.
# apply_state validates before its own label write, but this script writes
# labels of its own first (ensure_labels, then the surface re-match), so a note
# the grammar refuses tore the ticket: labels persisted, transition failed, and
# nothing rolls them back. Same helper apply_state uses, same `extra`.
B.check_meta_write(n["body"], dict(extra, note=note or None))

B.ensure_labels()

# Surface re-match (spec "Matching moment 2"): entering a dispatchable lane
# state re-runs identifier matching over the CURRENT body — the documented
# two-step registration flow (skeleton birth, body fleshed out afterward via
# `gh issue edit`) means register-time matching may have seen only a title.
# Add-only, labels only; relates edges are the sweep pass's backstop.
if to in B.DISPATCHABLE:
    _reg = B.surfaces_registry()
    if _reg is not None:
        _hits = [s_ for s_ in B.match_identifiers(
                     _reg, n["title"] + "\n" + B.strip_meta(n.get("body") or ""))
                 if s_ not in n["surfaces"]]
        for s_ in _hits:
            B.ensure_surface_label(s_)
            B.edit_labels(tid, add=(B.SURFACE_PREFIX + s_,))
        if _hits:
            print("surface: += %s" % " ".join(_hits))

lines = [B.apply_state(tickets, tid, to, note, extra_meta=extra)]

# Sweep: first active child pulls its epic chain to each parent's own
# in-flight state (PRE_PARK: architect queue → in-design, else in-progress).
# Any entry INTO an active state counts — an architect-lane child entering
# in-design is its epic's first active child exactly as an executor-lane
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
