# _board.py — shared backend for the issue-tracker toolkit (v7: GitHub SSOT).
#
# Imported by the inline python in board-*.sh (sys.path points here via
# $BOARD_SCRIPTS). Everything that talks to GitHub lives in this module:
# the snapshot query + normalization to the legacy node shape, the
# `board:meta` body block, state derivation, the transition legality table,
# and the mutation helpers. Scripts keep only their own validation/sweep
# logic on top.
#
# stdlib only. Every GitHub call shells out to `gh` (the toolkit's one
# external requirement) — tests substitute a PATH-shimmed mock `gh`.
import hashlib
import json
import os
import re
import subprocess
import time
import sys
from typing import NoReturn

# ── state vocabulary (v9: the E1 lane split — the single pre-v9 agent queue
#    split into ready-for-architect / in-design / ready-for-implementer) ──
OPEN_STATES = ("ready-for-architect", "in-design", "ready-for-implementer",
               "in-progress", "needs-human", "needs-info",
               "interactive-preferred", "in-review",
               "deferred")
TERMINAL = ("done", "wontfix")
STATES = OPEN_STATES + TERMINAL
# Actively-worked states: a close_candidate in one of these is normal
# mid-flight shape (part-1 PR merged, part 2 coming) — surfaces that nag or
# relocate (lint WARN, kanban column) skip them; passive displays still mark.
ACTIVE = ("in-design", "in-progress", "in-review")
# The two dispatchable lane queues — the eligibility predicate, slot
# accounting, and every ELIGIBLE display key off this tuple.
DISPATCHABLE = ("ready-for-architect", "ready-for-implementer")
BIRTH = ("ready-for-architect", "ready-for-implementer", "needs-info",
         "needs-human", "interactive-preferred", "deferred")
# Park discriminant — WHO UNPARKS IT (three addresses): the human as
# themselves (a decision or a real-world input) → needs-human; knowledge
# work anyone could do → needs-info; missing/broken design an AGENT can
# author → ready-for-architect. Ongoing steering → interactive-preferred.
NOTE_REQUIRED = ("needs-human", "needs-info", "interactive-preferred", "wontfix")
# Edge-keyed note requirement (E1 transitions 2/4/5 + the QAgent edge):
# these lane-crossing edges enter states that are note-free at birth, so
# the state-keyed NOTE_REQUIRED cannot express them.
EDGE_NOTE_REQUIRED = {
    ("in-design", "ready-for-implementer"),
    ("ready-for-implementer", "ready-for-architect"),
    ("in-progress", "ready-for-architect"),
    ("in-review", "ready-for-architect"),
}
# Convergence-counted escalation edges: a SECOND traversal of the same
# edge on one ticket converts to a needs-human park (board-transition
# enforces; count resets at the last [answers] comment).
CONVERGENCE_EDGES = EDGE_NOTE_REQUIRED - {("in-design", "ready-for-implementer")}
# Park-return targets (E1 transition 7): written into pre-park: meta at
# needs-human park time; board-answer returns the ticket there. Always an
# IN-FLIGHT state — returning to a dispatchable queue would race the sweep
# onto a second worker.
PRE_PARK = {
    "ready-for-architect": "in-design",
    "in-design": "in-design",
    "ready-for-implementer": "in-progress",
    "in-progress": "in-progress",
    "in-review": "in-review",
}
# Park states — the ones whose exit is somebody ELSE's action (a human
# decision, an information hunt, ongoing steering, a deliberate defer).
# BIRTH above is the other longhand twin of this tuple — a park state added
# here almost always belongs there too.
PARKED = ("needs-info", "needs-human", "interactive-preferred", "deferred")
# What an active child may pull its parent epic out of. The two lane queues,
# plus exactly one park — and the discriminant is the E2 park contract, not
# "epics have no workers" (they do: recomposition claims and scale reviewers
# bind to epics and park them).
#   needs-human            the session-resume contract — a bound worker waits
#                          on the answer, and the sweep's RELAY pass selects
#                          on THIS state to find it. Unparking would delete
#                          the human's question and drop the epic out of that
#                          queue while its worker sits idle.
#   interactive-preferred  a claim on the human's live attention.
#   deferred               a deliberate "not now" decision.
#   needs-info             fold-and-recut: NO bound worker and no relay
#                          entry by contract. On an epic it is the reconciling
#                          Architect's release exit ("reconciled: … — waiting
#                          on children"), and a child going active is
#                          literally the information whose absence that park
#                          names. The pull IS the wake.
# The other bookkeeping unpark is recompose_epics, which wakes a parked epic
# of ANY kind when its last child lands — nothing but a recomposition verdict
# can close an epic, so no one else ever would. Both preserve what the park
# owned by folding its note into their own (see _epic_note).
PULL_FROM = DISPATCHABLE + ("needs-info",)
LEGAL = {
    "ready-for-architect":   {"in-design", "needs-info", "needs-human",
                              "interactive-preferred", "wontfix", "deferred"},
    # in-design: the Architect's in-flight state. Exit = transition 2/3
    # (plan handoff / down-shortcircuit / decompose-epic) or a park.
    # done / in-review: EPIC-ONLY (E2 recomposition verdicts — the scoped
    # terminal-authority exception; board-transition enforces the guard).
    "in-design":             {"ready-for-implementer", "needs-info",
                              "needs-human", "interactive-preferred",
                              "wontfix", "deferred", "done", "in-review"},
    "ready-for-implementer": {"in-progress", "ready-for-architect",
                              "needs-info", "needs-human",
                              "interactive-preferred", "wontfix", "deferred"},
    "in-progress":           {"ready-for-architect", "needs-info",
                              "needs-human", "interactive-preferred",
                              "in-review", "done", "wontfix", "deferred"},
    "needs-info":            {"ready-for-architect", "ready-for-implementer",
                              "in-progress", "needs-human",
                              "interactive-preferred", "wontfix", "deferred"},
    # done from needs-human: the spike handoff — a finished spike parks
    # needs-human "findings ready" and the human closes it after reading
    # (done is the manual flip for non-PR work). Human-only in practice:
    # worker doctrine forbids terminal states.
    # in-design / in-review from needs-human: the pre-park returns
    # (board-answer reads pre-park: meta — E1 transition 7).
    "needs-human":           {"ready-for-architect", "ready-for-implementer",
                              "in-progress", "in-design", "in-review",
                              "needs-info", "interactive-preferred",
                              "done", "wontfix", "deferred"},
    "interactive-preferred": {"ready-for-architect", "ready-for-implementer",
                              "in-progress", "needs-info", "needs-human",
                              "wontfix", "deferred"},
    # ready-for-architect from in-review: the QAgent's design-gap
    # escalation (E1 third address; convergence-counted).
    "in-review":             {"in-progress", "ready-for-architect",
                              "done", "wontfix",
                              "deferred", "needs-info", "needs-human"},
    "deferred":        {"ready-for-architect", "ready-for-implementer",
                        "needs-info", "needs-human", "interactive-preferred",
                        "wontfix"},
    "done":            set(),   # terminal
    "wontfix":         set(),   # terminal
}
# Off-machine states a raw GitHub issue can be in (lint FAILs; transition
# repairs them by treating both as "any open state is reachable").
UNTRACKED = "untracked"   # open, zero status:* labels
CONFLICT = "conflict"     # open, two+ status:* labels

STATUS_PREFIX = "status:"
STATUS_COLORS = {  # ensure_labels palette (hex, no '#')
    "ready-for-architect": "006b75",
    "in-design":           "bfd4f2",
    "ready-for-implementer": "0e8a16",
    "in-progress":     "1d76db",
    "in-review":       "5319e7",
    "needs-human":     "d93f0b",
    "interactive-preferred": "d4c5f9",
    "needs-info":      "fbca04",
    "deferred":        "c5def5",
}

# Priority is the board's second managed label family: exactly one
# priority:P0..P3 per ticket (P0 = drop everything, P3 = someday). String
# order IS priority order, so plain sorts stay correct in shell/python/JS.
# Registration forces a grade; board-priority.sh swaps it; lint WARNs a
# missing grade (legacy tickets backfill gradually) and FAILs a double one.
PRIORITY_PREFIX = "priority:"
PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_COLORS = {  # ensure_labels palette (hex, no '#')
    "P0": "b60205",
    "P1": "d93f0b",
    "P2": "fbca04",
    "P3": "c2e0c6",
}

# Categories: bug/enhancement are GitHub defaults; spike (the exploration
# lane — deliverable is findings, never a merge) and env-issue (E2:
# environmental friction, fire-and-continue registration) are
# board-managed, so ensure_labels creates them.
CATEGORIES = ("bug", "enhancement", "spike", "env-issue")
SPIKE_COLOR = "f9d0c4"
ENV_ISSUE_COLOR = "e4a0f7"

# Surfaces: the board's third managed label family. A surface is a named
# contested code seam the CONSUMER repo declares in .doperpowers/surfaces.md
# (read from the default branch — an entry takes effect when its PR lands,
# never from a working tree). A ticket carrying `surface:<name>` is
# serialized by implement-dispatch: one in-flight implement worker per
# surface. Closed vocabulary — a surface label with no registry entry is a
# lint FAIL. No registry file → surfaces_registry() is None → every surface
# feature is inert (the opt-in contract).
SURFACE_PREFIX = "surface:"
SURFACE_COLOR = "e99695"
SURFACE_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

META_RE = re.compile(r"\n?<!-- board:meta\n(.*?)\n-->\s*$", re.S)
META_KEYS = ("spawned-by", "relates-to", "branch", "pr", "plan", "pre-park",
             "parent-pin", "note")


def die(msg) -> NoReturn:
    sys.stderr.write("error: %s\n" % msg)
    raise SystemExit(1)


def repo():
    r = os.environ.get("BOARD_REPO")
    if not r:
        die("BOARD_REPO is unset — _lib.sh resolves it; source _lib.sh first")
    return r


# ── gh plumbing ──────────────────────────────────────────────────────────
def gh(args, input_text=None):
    """Run `gh <args>`; return stdout. Fail loud with gh's own stderr."""
    try:
        p = subprocess.run(["gh"] + args, capture_output=True, text=True,
                           input=input_text)
    except FileNotFoundError:
        die("`gh` not found — the board lives on GitHub; install/auth the GitHub CLI")
    if p.returncode != 0:
        die("gh %s failed:\n%s" % (" ".join(args[:3]), p.stderr.strip() or p.stdout.strip()))
    return p.stdout


def graphql(query, **variables):
    args = ["api", "graphql", "-f", "query=%s" % query]
    for k, v in variables.items():
        # -F types ints/bools; strings must stay -f (a numeric-looking cursor
        # must not become an Int).
        if isinstance(v, bool):
            args += ["-F", "%s=%s" % (k, "true" if v else "false")]
        elif isinstance(v, int):
            args += ["-F", "%s=%d" % (k, v)]
        else:
            args += ["-f", "%s=%s" % (k, v)]
    out = gh(args)
    data = json.loads(out)
    if data.get("errors"):
        die("GraphQL: %s" % "; ".join(e.get("message", "?") for e in data["errors"]))
    return data["data"]


# ── board:meta body block ────────────────────────────────────────────────
def parse_meta(body):
    """The trailing `<!-- board:meta ... -->` block → dict (absent keys omitted)."""
    m = META_RE.search(body or "")
    meta = {}
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k in META_KEYS and v:
            meta[k] = v
    return meta


def strip_meta(body):
    """The body WITHOUT its trailing board:meta block — the ticket's own text,
    with the board's bookkeeping removed."""
    return META_RE.sub("", body or "").rstrip("\n")


def contract_hash(body):
    """The id a `parent-pin:` names: sha256/12 over the ticket's text with
    board:meta STRIPPED.

    The meta block is the board writing to itself, and it moves constantly —
    recompose_epics clears `pr:`/`branch:` on every recomposition cycle alone.
    Hashing the whole body therefore reported "the parent contract changed" at
    every cycle, and an Architect who adjudicates a fake diff every time soon
    stops reading the real one. What a child inherits is the contract text, so
    that is what the pin identifies."""
    return hashlib.sha256(strip_meta(body).encode("utf-8")).hexdigest()[:12]


def render_body(body, meta):
    """Body with its meta block replaced by `meta` (dropped when meta is empty).
    Everything outside the block is preserved byte-for-byte."""
    base = strip_meta(body)
    meta = {k: v for k, v in meta.items() if v}
    if not meta:
        return base + ("\n" if base else "")
    block = "\n".join("%s: %s" % (k, meta[k]) for k in META_KEYS if k in meta)
    return "%s\n\n<!-- board:meta\n%s\n-->\n" % (base, block)


def _nums(val):
    """'#12 #7' / '12,7' → ['12', '7'] (issue-number refs in a meta value)."""
    return re.findall(r"\d+", val or "")


# ── snapshot: one paginated query → legacy-shaped tickets dict ───────────
_SNAPSHOT_QUERY = """
query($owner:String!, $name:String!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    issues(first:100, after:$cursor, states:[OPEN,CLOSED],
           orderBy:{field:CREATED_AT, direction:ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id number title body url state stateReason createdAt updatedAt
        labels(first:50) { nodes { name } }
        assignees(first:10) { nodes { login } }
        parent { number }
        blockedBy(first:50) { nodes { number } }
        closedByPullRequestsReferences(first:20, includeClosedPrs:true) {
          totalCount
          nodes { number url state isDraft }
        }
        timelineItems(itemTypes:[CROSS_REFERENCED_EVENT], first:40) {
          totalCount
          nodes {
            ... on CrossReferencedEvent {
              source { __typename ... on PullRequest { number url state isDraft } }
            }
          }
        }
      }
    }
  }
}
"""

_snapshot_cache = None


def derive_state(gh_state, state_reason, status_labels):
    if gh_state == "CLOSED":
        return "wontfix" if state_reason in ("NOT_PLANNED", "DUPLICATE") else "done"
    # An OPEN issue must carry exactly one *open*-state label — a lone
    # status:done/status:wontfix on an open issue (e.g. legacy merge automation
    # that labels instead of closing) is a conflict, not a state.
    if len(status_labels) == 1 and status_labels[0] in OPEN_STATES:
        return status_labels[0]
    return CONFLICT if status_labels else UNTRACKED


def snapshot(refresh=False):
    """All issues, normalized to the v6 node shape keyed by str(number).
    Cached per process — write scripts fetch once, mutate GitHub, and report
    from their own knowledge of what they changed."""
    global _snapshot_cache
    if _snapshot_cache is not None and not refresh:
        return _snapshot_cache
    owner, name = repo().split("/", 1)
    tickets, cursor = {}, None
    while True:
        kw = {"owner": owner, "name": name}
        if cursor:
            kw["cursor"] = cursor
        page = graphql(_SNAPSHOT_QUERY, **kw)["repository"]["issues"]
        for it in page["nodes"]:
            labels = [l["name"] for l in it["labels"]["nodes"]]
            status = [l[len(STATUS_PREFIX):] for l in labels if l.startswith(STATUS_PREFIX)]
            prios = [l[len(PRIORITY_PREFIX):] for l in labels if l.startswith(PRIORITY_PREFIX)]
            meta = parse_meta(it["body"])
            spawned = _nums(meta.get("spawned-by"))
            # Native GitHub PR linkage — closesByPR fills the merge-autoclose gap
            # (a "Closes #N" merge never writes a pr: meta), cross-refs catch PRs
            # that merely mention the issue. Keyed by number → deduped; a PR that
            # both closes and cross-refs keeps the stronger "closes" relation.
            closes, timeline = it["closedByPullRequestsReferences"], it["timelineItems"]
            prs = {}
            for pr in closes["nodes"]:
                if pr:
                    prs[pr["number"]] = {"num": pr["number"], "url": pr["url"],
                                         "state": pr["state"],
                                         "draft": pr.get("isDraft", False), "rel": "closes"}
            for tl in timeline["nodes"]:
                src = (tl or {}).get("source") or {}
                if src.get("__typename") == "PullRequest":
                    prs.setdefault(src["number"], {"num": src["number"], "url": src["url"],
                                                   "state": src["state"],
                                                   "draft": src.get("isDraft", False), "rel": "ref"})
            # Both PR connections are fetched capped (first:20/40, unpaginated).
            # Truncation is harmless for DISPLAY, but the close-candidate
            # predicate asserts "ALL linked PRs landed" — over a truncated list
            # that claim is unfounded (an uncounted PR may be open), so the
            # predicate requires the fetch to be provably complete.
            prs_complete = (closes["totalCount"] <= len(closes["nodes"])
                            and timeline["totalCount"] <= len(timeline["nodes"]))
            pr_list = sorted(prs.values(), key=lambda p: p["num"])
            state = derive_state(it["state"], it.get("stateReason"), status)
            tickets[str(it["number"])] = {
                "id": it["id"],
                "title": it["title"],
                "state": state,
                "status_labels": status,
                # priority: the single valid grade, else None; priority_labels
                # keeps the raw list so lint can tell missing from conflicted.
                "priority": prios[0] if len(prios) == 1 and prios[0] in PRIORITIES else None,
                "priority_labels": prios,
                "category": next((c for c in CATEGORIES if c in labels),
                                 "enhancement"),
                "note": meta.get("note"),
                "parent": str(it["parent"]["number"]) if it.get("parent") else None,
                "blocked_by": [str(b["number"]) for b in it["blockedBy"]["nodes"]],
                "spawned_by": spawned[0] if spawned else None,
                "relates_to": _nums(meta.get("relates-to")),
                "branch": meta.get("branch"),
                "pr": meta.get("pr"),
                "prs": pr_list,
                # Derived, never a label: open ticket whose linked PRs all
                # landed or died, with at least one actually MERGED (all-CLOSED
                # = abandoned attempts, not delivered work). A triage cue —
                # closing stays a human/orchestrator call. prs_complete guards
                # the "all" against a capped fetch (see above): when truncated,
                # fail conservative — no candidate rather than a false one.
                "close_candidate": state not in TERMINAL and bool(pr_list)
                    and prs_complete
                    and all(p["state"] in ("MERGED", "CLOSED") for p in pr_list)
                    and any(p["state"] == "MERGED" for p in pr_list),
                "surfaces": [l[len(SURFACE_PREFIX):] for l in labels
                             if l.startswith(SURFACE_PREFIX)],
                "labels": [l for l in labels
                           if not l.startswith(STATUS_PREFIX)
                           and not l.startswith(PRIORITY_PREFIX)
                           and not l.startswith(SURFACE_PREFIX)
                           and l not in CATEGORIES],
                "assignees": [a["login"] for a in it["assignees"]["nodes"]],
                "created": it["createdAt"][:10],
                "updated": it["updatedAt"][:10],
                # Full precision alongside the display date: the sweep's
                # IMPACT pass uses it as a per-child scan cursor, and a
                # day-granular value would stall every re-read within a day.
                "updated_at": it["updatedAt"],
                "url": it["url"],
                "body": it["body"] or "",
            }
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    _snapshot_cache = tickets
    return tickets


def resolve(ref, tickets=None):
    """'#42' / '42' → '42', validated against the snapshot when given."""
    n = str(ref).lstrip("#")
    if not n.isdigit():
        die("not an issue number: %s" % ref)
    if tickets is not None and n not in tickets:
        die("unknown issue: #%s" % n)
    return n


# ── label management ─────────────────────────────────────────────────────
def ensure_labels():
    """Create any missing managed labels — status:* AND priority:* — in one
    idempotent pass (a single `gh label list` call)."""
    have = {l["name"] for l in json.loads(
        gh(["label", "list", "-R", repo(), "--json", "name", "--limit", "200"]))}
    want = [(STATUS_PREFIX + s, c, "issue-tracker board state")
            for s, c in STATUS_COLORS.items()]
    want += [(PRIORITY_PREFIX + p, c, "issue-tracker board priority")
             for p, c in PRIORITY_COLORS.items()]
    want += [("spike", SPIKE_COLOR,
              "issue-tracker board category: exploration spike — "
              "deliverable is findings, never a merge")]
    want += [("env-issue", ENV_ISSUE_COLOR,
              "issue-tracker board category: environmental friction — "
              "fire-and-continue; default birth needs-human")]
    for name, color, desc in want:
        # GitHub rejects label descriptions over 100 chars (422) — fail
        # here, at the string, not remotely mid-registration.
        assert len(desc) <= 100, "label %s description exceeds 100 chars" % name
        if name not in have:
            gh(["label", "create", name, "-R", repo(), "--color", color,
                "--description", desc, "--force"])


# ── mutations (the only write path — see the Hard Gate in SKILL.md) ──────
def edit_labels(num, remove=(), add=()):
    args = ["issue", "edit", num, "-R", repo()]
    for l in remove:
        args += ["--remove-label", l]
    for l in add:
        args += ["--add-label", l]
    if len(args) > 4:
        gh(args)


# ── surfaces registry (.doperpowers/surfaces.md on the default branch) ───
def _surfaces_ref():
    """The ref surfaces.md is read from: $SURFACES_REF (tests), else the
    remote default branch. Entries take effect when their PR LANDS — a
    working-tree or feature-branch entry has no effect (spec M1)."""
    ref = os.environ.get("SURFACES_REF")
    if ref:
        return ref
    r = subprocess.run(["git", "symbolic-ref", "-q", "--short",
                        "refs/remotes/origin/HEAD"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    for cand in ("origin/main", "origin/master"):
        if subprocess.run(["git", "rev-parse", "--verify", "-q", cand],
                          capture_output=True).returncode == 0:
            return cand
    return None


_surfaces_cache = ("unset",)


def surfaces_registry():
    """Parsed .doperpowers/surfaces.md → {name: {"paths": [...],
    "identifiers": [...], "born_of": str, "note": str}} — or None when the
    file (or a readable ref) is absent, which switches every surface
    feature off. Cached per process like snapshot()."""
    global _surfaces_cache
    if _surfaces_cache[0] != "unset":
        return _surfaces_cache[0]
    reg = None
    ref = _surfaces_ref()
    if ref:
        # Refresh the tracking ref first (best-effort): none of the board
        # scripts otherwise fetch, so a registry entry merged remotely would
        # stay invisible to a long-lived clone indefinitely. Offline or slow
        # remotes degrade to the cached ref, never to an error. $SURFACES_REF
        # (tests / explicit pins) skips the fetch — the override IS the pin.
        if not os.environ.get("SURFACES_REF") and "/" in ref:
            # Cross-process fetch stamp: a dispatch sweep runs a fresh
            # python per ticket, so a per-process cache alone would fetch
            # N times per tick (N x 30s worst case offline). One fetch per
            # SURFACES_FETCH_TTL seconds (default 300) across processes.
            stamp = os.path.join(
                os.environ.get("DAEMON_HOME",
                               os.path.expanduser(
                                   "~/.claude/orchestrating-daemons")),
                ".surfaces-fetch-stamp")
            ttl = int(os.environ.get("SURFACES_FETCH_TTL") or 300)
            try:
                fresh = (time.time() - os.stat(stamp).st_mtime) < ttl
            except OSError:
                fresh = False
            if not fresh:
                remote, _, branch = ref.partition("/")
                try:
                    subprocess.run(["git", "fetch", "--quiet", remote, branch],
                                   capture_output=True, timeout=30, check=False)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.makedirs(os.path.dirname(stamp), exist_ok=True)
                    with open(stamp, "w"):
                        pass
                    os.utime(stamp, None)
                except OSError:
                    pass
        r = subprocess.run(["git", "show", "%s:.doperpowers/surfaces.md" % ref],
                           capture_output=True, text=True)
        if r.returncode == 0:
            reg, cur = {}, None
            for line in r.stdout.splitlines():
                m = re.match(r"^##\s+(\S+)\s*$", line)
                if m:
                    cur = {"paths": [], "identifiers": [],
                           "born_of": "", "note": ""}
                    reg[m.group(1)] = cur
                    continue
                if cur is None:
                    continue
                m = re.match(r"^-\s*(paths|identifiers|born-of|note):\s*(.*)$",
                             line)
                if not m:
                    continue
                key, val = m.group(1), m.group(2).strip()
                if key in ("paths", "identifiers"):
                    cur[key] = [p.strip() for p in val.split(",") if p.strip()]
                else:
                    cur[key.replace("-", "_")] = val
    _surfaces_cache = (reg,)
    return reg


def match_identifiers(registry, text):
    """Surface names whose identifiers appear in `text` as whole words
    (case-sensitive — the register/transition matching moments)."""
    hits = []
    for name, entry in (registry or {}).items():
        for ident in entry["identifiers"]:
            if re.search(r"\b%s\b" % re.escape(ident), text or ""):
                hits.append(name)
                break
    return sorted(hits)


def _glob_re(pat):
    """One surfaces.md path glob → regex: `**` crosses `/`, `*` does not,
    `?` is one non-slash char. Hand-rolled (fnmatch's `*` crosses `/`)."""
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^%s$" % "".join(out))


def match_paths(registry, paths):
    """Surface names whose path globs match any of `paths` (a PR diff's
    file list; a rename should contribute both its old and new path)."""
    hits = []
    for name, entry in (registry or {}).items():
        pats = [_glob_re(p) for p in entry["paths"]]
        if any(p.match(path) for p in pats for path in paths):
            hits.append(name)
    return sorted(hits)


def live_bound_tickets(include_reviewers=True):
    """Ticket numbers (str) with a live bound worker (registry meta status
    working/blocked). Surface-driven BODY writes (relates edges) defer on
    these — update_meta is a full-body read-modify-write and must never race
    a live worker's own meta write (spec H2). Reviewer/lander species write
    meta too, so they count by default; occupancy checks pass
    include_reviewers=False (their ticket's in-review STATE already covers
    them there)."""
    import glob
    home = os.environ.get("DAEMON_HOME",
                          os.path.expanduser("~/.claude/orchestrating-daemons"))
    live = set()
    for p in glob.glob(os.path.join(home, "*.json")):
        if p.endswith(".reply.json"):
            continue
        try:
            with open(p) as f:
                m = json.load(f)
        except (ValueError, OSError):
            continue
        if not include_reviewers:
            name = str(m.get("name") or "")
            if name.startswith(("review-pr-", "review-epic-", "land-pr-")):
                continue
        if m.get("status") in ("working", "blocked"):
            t = str(m.get("ticket") or "").lstrip("#")
            if t:
                live.add(t)
    return live


def ensure_surface_label(name):
    """Create the surface:<name> label if missing (idempotent; one list
    call per process would be nicer but registration is rare)."""
    label = SURFACE_PREFIX + name
    have = {l["name"] for l in json.loads(
        gh(["label", "list", "-R", repo(), "--json", "name", "--limit", "200"]))}
    if label not in have:
        gh(["label", "create", label, "-R", repo(), "--color", SURFACE_COLOR,
            "--description", "issue-tracker contested surface (serialized dispatch)",
            "--force"])


def set_state_label(num, node, to):
    """Swap the status:* label set to exactly `to` (repairs conflict/untracked)."""
    stale = [STATUS_PREFIX + s for s in node["status_labels"] if s != to]
    add = [] if to in node["status_labels"] else [STATUS_PREFIX + to]
    edit_labels(num, remove=stale, add=add)


def set_priority_label(num, node, to):
    """Swap the priority:* label set to exactly `to` (repairs a double label)."""
    stale = [PRIORITY_PREFIX + p for p in node["priority_labels"] if p != to]
    add = [] if to in node["priority_labels"] else [PRIORITY_PREFIX + to]
    edit_labels(num, remove=stale, add=add)


def close(num, state):
    reason = "completed" if state == "done" else "not planned"
    gh(["issue", "close", num, "-R", repo(), "--reason", reason])


def comment(num, text):
    gh(["issue", "comment", num, "-R", repo(), "--body-file", "-"], input_text=text)


def comments(num):
    """EVERY comment on issue <num>, oldest first, normalized to the field
    names the board's comment-controlled scans use: id, body,
    authorAssociation.

    REST + `--paginate`, never `gh issue view --json comments`: that serves a
    SINGLE page, and three scans read it as the whole log — the convergence
    count here, and the sweep's IMPACT proposal and dedupe-marker reads. Past
    ~100 comments a truncated read silently drops traversals (extra bounces
    the convergence rule exists to stop), proposals, and markers. The IMPACT
    pass makes it permanent: its cursor would persist seen=<updatedAt> for a
    child whose proposal it never reached, so nothing brings that child back.
    A failed page is not a short read — gh() dies on non-zero exit, which
    kills the pass before any cursor write, so a cursor only ever records a
    COMPLETE read.

    `--slurp` is not optional. Bare `--paginate` streams each page as its own
    top-level array, concatenated — valid JSON documents back to back, which
    json.loads rejects with "Extra data" the moment a second page exists. That
    fails on precisely the long trails this read was written for. --slurp wraps
    the pages in one outer array instead, so the result is a list of
    page-lists and flattening it one level yields the log. (gh >= 2.53; an
    older gh rejects the flag outright, and gh() surfaces that stderr rather
    than half-reading.)"""
    pages = json.loads(gh(["api", "repos/%s/issues/%s/comments" % (repo(), num),
                           "--paginate", "--slurp"]) or "[]")
    raw = [c for page in pages for c in (page or [])]
    return [{"id": c.get("id"),
             "body": c.get("body") or "",
             "createdAt": c.get("created_at") or "",
             "authorAssociation": c.get("author_association") or ""}
            for c in raw if isinstance(c, dict)]


def set_body(num, body):
    gh(["issue", "edit", num, "-R", repo(), "--body-file", "-"], input_text=body)


def update_meta(num, node, **updates):
    """Read-modify-write the node's board:meta block. `None` deletes a key.
    Refreshes node['body']/meta-derived fields in place."""
    meta = parse_meta(node["body"])
    for k, v in updates.items():
        if v is None:
            meta.pop(k, None)
        else:
            meta[k] = v
    body = render_body(node["body"], meta)
    if body != node["body"]:
        set_body(num, body)
        node["body"] = body


def add_sub_issue(parent_node, child_node, replace=False):
    graphql("""mutation($p:ID!, $c:ID!, $r:Boolean) {
      addSubIssue(input:{issueId:$p, subIssueId:$c, replaceParent:$r}) {
        issue { number } } }""",
            p=parent_node["id"], c=child_node["id"], r=replace)


def remove_sub_issue(parent_node, child_node):
    graphql("""mutation($p:ID!, $c:ID!) {
      removeSubIssue(input:{issueId:$p, subIssueId:$c}) {
        issue { number } } }""",
            p=parent_node["id"], c=child_node["id"])


def add_blocked_by(node, blocker_node):
    graphql("""mutation($i:ID!, $b:ID!) {
      addBlockedBy(input:{issueId:$i, blockingIssueId:$b}) {
        issue { number } } }""",
            i=node["id"], b=blocker_node["id"])


def remove_blocked_by(node, blocker_node):
    graphql("""mutation($i:ID!, $b:ID!) {
      removeBlockedBy(input:{issueId:$i, blockingIssueId:$b}) {
        issue { number } } }""",
            i=node["id"], b=blocker_node["id"])


# ── shared derivations (v6 semantics, snapshot-shaped input) ─────────────
def children(tickets, p):
    return [t for t, n in tickets.items() if n.get("parent") == p]


def epics(tickets):
    return {n["parent"] for n in tickets.values() if n.get("parent")}


def eligible(tickets, tid):
    n = tickets[tid]
    if tid in epics(tickets):
        # E2 carve-out: dispatchable epic states are exactly
        # ready-for-architect awaiting recomposition (children all
        # terminal — a queued corrective child must pull the epic back out
        # of the dispatch pool before an Architect claims a moving target)
        # or awaiting reconciliation (the sweep's reconciliation-due
        # return — children may still be active).
        if n["state"] != "ready-for-architect":
            return False
        if not recomposition_ready(tickets, tid) \
           and not (n.get("note") or "").startswith("reconciliation-due:"):
            return False
    elif n["state"] not in DISPATCHABLE:
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"])


def ancestors(tickets, t):
    seen = set()
    p = tickets[t].get("parent")
    while p and p in tickets and p not in seen:
        seen.add(p)
        p = tickets[p].get("parent")
    return seen


# ── the transition core (state write + note + sweeps) ────────────────────
def apply_state(tickets, tid, to, why, extra_meta=None, bookkeeping=False):
    """Write one state change to GitHub + the in-memory snapshot; return the
    human line. Notes ride the meta block (current) and a comment (audit);
    extra_meta lets the caller fold branch/pr into the same body write."""
    n = tickets[tid]
    old = n["state"]
    if to in TERMINAL:
        # strip status labels first so a closed issue never carries one
        edit_labels(tid, remove=[STATUS_PREFIX + s for s in n["status_labels"]])
        close(tid, to)
    else:
        set_state_label(tid, n, to)
    updates = {"note": why or None}
    updates.update(extra_meta or {})
    update_meta(tid, n, **updates)
    if why:
        if bookkeeping:
            # Board bookkeeping on an epic (the recomposition/reconciliation
            # return): the marker is deliberately NOT the "[board] from → to:"
            # format — the convergence counter greps that format, and a
            # mechanical return must never count as a worker escalation
            # traversal. pull_epics writes plain "[board] <to>:" comments
            # instead: no pull edge is a convergence edge, so it needs no
            # exemption from the counter.
            comment(tid, "[board-epic] %s: %s" % (to, why))
        elif (old, to) in CONVERGENCE_EDGES:
            comment(tid, "[board] %s → %s: %s" % (old, to, why))
        else:
            comment(tid, "[board] %s: %s" % (to, why))
    n["state"], n["status_labels"] = to, ([] if to in TERMINAL else [to])
    n["note"] = why or None
    return "#%s: %s → %s" % (tid, old, to)


def _epic_note(node, why):
    """Bookkeeping note for an epic write that UNPARKS the epic — the park's
    own note (a human's pending question, the reconciling Architect's
    'waiting on children' line) is folded in rather than overwritten. Only
    a park's note is somebody else's; an in-flight epic's note is the
    board's own previous bookkeeping line and is simply replaced."""
    old = node.get("note")
    if node["state"] in PARKED and old:
        return "%s (was: %s)" % (why, old)
    return why


def pull_epics(tickets, tid, lines):
    """First active child pulls its parent chain out of PULL_FROM into its
    lane's in-flight state — PRE_PARK's queue -> in-flight mapping, reused
    rather than a second table (ready-for-architect -> in-design;
    ready-for-implementer and the one pullable park have no PRE_PARK entry
    and default to in-progress, their existing in-flight state). Writing
    straight to "in-progress" regardless of the parent's queue used to
    strand a ready-for-architect epic outside every state its own lane's
    happy path or park returns ever produce.

    The walk stops at every OTHER park (see PULL_FROM for the contract that
    discriminates them), exactly as pass_impact's UNCLAIMABLE skip does:
    those parks own a bound session or a claim on the human, and unparking
    one would delete its note and drop the epic out of the queue its owner
    is waiting in. Such an ancestor is woken by whoever owns the park, or
    by recompose_epics when the last child lands; never by a sibling going
    active.

    This is the board's own bookkeeping on an epic — never dispatched,
    never gated — the same latitude recompose_epics already has for its
    epic-return writes; it does not answer to LEGAL, which governs what a
    WORKER or human may transition to by hand. (An earlier version of this
    fix asserted `to in LEGAL[pstate]` and, to satisfy that, added
    deferred -> in-progress to LEGAL itself — which silently legalized a
    human/worker skipping the queue and the gate on a deferred ticket.
    That was the wrong invariant to assert; reverted.) The real invariant
    is structural, not legal: an epic pull only ever lands on an in-flight
    state (ACTIVE), never a queue or park — asserted below so a future
    PULL_FROM addition whose PRE_PARK-or-default target resolves outside
    ACTIVE fails loud instead of silently routing an epic somewhere
    nonsensical.
    """
    p = tickets[tid].get("parent")
    while p and p in tickets and tickets[p]["state"] in PULL_FROM:
        pstate = tickets[p]["state"]
        if pstate == "ready-for-architect" \
           and (tickets[p].get("note") or "").startswith("reconciliation-due:"):
            # An UNCLAIMED reconciliation return (the sweep's IMPACT pass put
            # the epic here; the [board-epic] reconcile: marker already says
            # the proposal is consumed, but no Architect has read it yet).
            # Pulling it lands the epic in in-design — out of the lane queue
            # and out of the dispatch pool — so nobody would read that proposal,
            # and every later proposal on this epic would defer to final
            # recomposition. The gate is the NOTE, not the state: a
            # recomposition-due epic (all children terminal) IS pulled back by
            # a corrective child, deliberately. The walk stops here for the
            # same reason it stops on any unpullable parent — an ancestor is
            # pulled by its own child going active, not through a parent that
            # stayed put.
            break
        to = PRE_PARK.get(pstate, "in-progress")
        assert to in ACTIVE, (
            "pull_epics: %s -> %s is not an in-flight state (PRE_PARK "
            "drifted out of sync with ACTIVE for a PULL_FROM state)" % (pstate, to))
        lines.append(apply_state(
            tickets, p, to, _epic_note(tickets[p], "epic: child #%s active" % tid)))
        p = tickets[p].get("parent")


def recomposition_ready(tickets, tid):
    """An epic whose every child is terminal awaits recomposition — E2:
    'required' = every child (no optionality machinery), and the old
    at-least-one-done guard is retired: an all-wontfix epic also wakes an
    Architect, whose verdict (done / wontfix / needs-human) replaces the
    guard's silent stall."""
    n = tickets.get(tid)
    if n is None or n["state"] in TERMINAL:
        return False
    kids = children(tickets, tid)
    return bool(kids) and all(tickets[k]["state"] in TERMINAL for k in kids)


def recompose_epics(tickets, p, lines):
    """E2 replaces the mechanical epic auto-close: a parent is closed by an
    Architect's VERIFICATION against its own acceptance (recomposition),
    never by child bookkeeping. When the last child lands, the epic
    returns to ready-for-architect — the one state where epics are
    dispatchable — with the recomposition-due note. Bookkeeping latitude:
    exempt from LEGAL and from convergence counting ([board-epic] marker).

    The return also CLEARS the `pr` AND `branch` meta. Both describe the
    composition, and a composition that just changed voids both: `pr` holds
    the recomposition closure package, `branch` the integration ref that
    package's aggregate range is read from. Leaving `pr` let an Architect
    re-enter in-review without --pr (the gate accepts the stale value) and
    the scale-review sweep, which dedupes on exact package equality, would
    read the epic as already reviewed forever. Leaving `branch` let a scale
    reviewer check out a ref from an earlier cycle — or a leftover from a
    plan handoff or park that was never an integration branch at all — and
    review the wrong diff entirely. Clearing it makes provenance structural:
    any `branch` present at scale dispatch was supplied by the Architect THIS
    cycle, on the in-review entry, alongside the package.

    The reconciliation return (the sweep's IMPACT pass) deliberately clears
    NEITHER — that is not a recomposition cycle.

    An epic ALREADY sitting in ready-for-architect still gets the
    bookkeeping; only the state write is skipped (it is already there, and
    apply_state's label swap degenerates to nothing anyway). It used to be
    skipped whole, back when the return was purely a state change and the
    guard was mere observability. It is not that any more: the return now
    carries CYCLE-SCOPED writes, and a corrective child landing before an
    Architect claims the queued epic — the scale-review corrective return, or
    an unclaimed reconciliation return — is exactly a new cycle. Skipping it
    left the previous cycle's integration `branch` (and package) live into the
    next one, and dropped the `[board-epic] ready-for-architect:` comment that
    resets the convergence count, so the NEXT legitimate corrective-child
    escalation read as a second traversal and was parked needs-human."""
    while p and p in tickets:
        if not recomposition_ready(tickets, p):
            break
        n = tickets[p]
        queued = n["state"] == "ready-for-architect"
        meta = parse_meta(n["body"])
        # Idempotence discriminator: this cycle's bookkeeping has already run
        # when the note is the recomposition-due one AND both cycle-scoped
        # metas are clear. Anything else — a reviewer's note, a surviving pr
        # or branch — means the writes are still owed. Re-running a `done`
        # transition on an already-terminal child (the finalize path) hits
        # this and stays silent.
        if queued and (n.get("note") or "").startswith("recomposition-due:") \
           and not meta.get("pr") and not meta.get("branch"):
            break
        line = apply_state(
            tickets, p, "ready-for-architect",
            _epic_note(n, "recomposition-due: all children terminal"),
            extra_meta={"pr": None, "branch": None},
            bookkeeping=True)
        lines.append(
            "#%s: already ready-for-architect — recomposition bookkeeping "
            "refreshed (new cycle)" % p if queued else line)
        # the chain walk ends here: an ancestor can only become ready when
        # THIS epic reaches terminal via its own recomposition verdict
        break


def newly_eligible(tickets, done_tid):
    out = []
    for t in sorted(tickets, key=int):
        n = tickets[t]
        if n["state"] in DISPATCHABLE and done_tid in n["blocked_by"] \
           and all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"]):
            out.append("now eligible: #%s  %s" % (t, " ".join(n["title"].split())))
    return out
