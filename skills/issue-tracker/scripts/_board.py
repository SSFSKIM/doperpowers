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
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

# ── state vocabulary (v8: blocked retired into needs-human; the park trio) ──
OPEN_STATES = ("ready-for-agent", "in-progress", "needs-human", "needs-info",
               "interactive-preferred", "in-review", "confident-ready",
               "deferred")
TERMINAL = ("done", "wontfix")
STATES = OPEN_STATES + TERMINAL
# Actively-worked states: a close_candidate in one of these is normal
# mid-flight shape (part-1 PR merged, part 2 coming) — surfaces that nag or
# relocate (lint WARN, kanban column) skip them; passive displays still mark.
ACTIVE = ("in-progress", "in-review")
BIRTH = ("ready-for-agent", "needs-info", "needs-human",
         "interactive-preferred", "deferred")
# Park discriminant — WHO UNPARKS IT: the human as themselves (a decision or
# a real-world input) → needs-human; knowledge work anyone could do →
# needs-info; ongoing steering, not one answer → interactive-preferred.
NOTE_REQUIRED = ("needs-human", "needs-info", "interactive-preferred", "wontfix")
PULLABLE = ("ready-for-agent", "needs-info", "needs-human",
            "interactive-preferred", "deferred")
LEGAL = {
    "ready-for-agent": {"in-progress", "needs-info", "needs-human",
                        "interactive-preferred", "wontfix", "deferred"},
    "in-progress":     {"needs-info", "needs-human", "interactive-preferred",
                        "in-review", "done", "wontfix", "deferred"},
    "needs-info":      {"ready-for-agent", "in-progress", "needs-human",
                        "interactive-preferred", "wontfix", "deferred"},
    "needs-human":     {"ready-for-agent", "in-progress", "needs-info",
                        "interactive-preferred", "wontfix", "deferred"},
    "interactive-preferred": {"ready-for-agent", "in-progress", "needs-info",
                        "needs-human", "wontfix", "deferred"},
    # needs-human reachable from in-review: the reviewing-prs review loop's
    # impasse/precondition escalations (protocol safety valve) — all its
    # parks route to needs-human. needs-info stays reachable here too, as a
    # human/legacy affordance; the review worker itself no longer writes it.
    "in-review":       {"in-progress", "confident-ready", "done", "wontfix",
                        "deferred", "needs-info", "needs-human"},
    # confident-ready: PR rigorously reviewed by the reviewing-prs loop.
    # Reachable ONLY from in-review (a review verdict presupposes an open PR);
    # deliberately NOT in ACTIVE — a confident-ready ticket whose PRs all
    # merged SHOULD surface as a close candidate (the finalize cue).
    "confident-ready": {"in-progress", "in-review", "done", "wontfix", "deferred"},
    "deferred":        {"ready-for-agent", "needs-info", "needs-human",
                        "interactive-preferred", "wontfix"},
    "done":            set(),   # terminal
    "wontfix":         set(),   # terminal
}
# Off-machine states a raw GitHub issue can be in (lint FAILs; transition
# repairs them by treating both as "any open state is reachable").
UNTRACKED = "untracked"   # open, zero status:* labels
CONFLICT = "conflict"     # open, two+ status:* labels

STATUS_PREFIX = "status:"
STATUS_COLORS = {  # ensure_labels palette (hex, no '#')
    "ready-for-agent": "0e8a16",
    "in-progress":     "1d76db",
    "in-review":       "5319e7",
    "confident-ready": "008672",
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
# lane — deliverable is findings, never a merge) is board-managed, so
# ensure_labels creates it.
CATEGORIES = ("bug", "enhancement", "spike")
SPIKE_COLOR = "f9d0c4"

META_RE = re.compile(r"\n?<!-- board:meta\n(.*?)\n-->\s*$", re.S)
META_KEYS = ("spawned-by", "relates-to", "branch", "pr", "note")


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


def render_body(body, meta):
    """Body with its meta block replaced by `meta` (dropped when meta is empty).
    Everything outside the block is preserved byte-for-byte."""
    base = META_RE.sub("", body or "").rstrip("\n")
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
                "labels": [l for l in labels
                           if not l.startswith(STATUS_PREFIX)
                           and not l.startswith(PRIORITY_PREFIX)
                           and l not in CATEGORIES],
                "assignees": [a["login"] for a in it["assignees"]["nodes"]],
                "created": it["createdAt"][:10],
                "updated": it["updatedAt"][:10],
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
    for name, color, desc in want:
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
    if tid in epics(tickets) or n["state"] != "ready-for-agent":
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
def apply_state(tickets, tid, to, why, extra_meta=None):
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
        comment(tid, "[board] %s: %s" % (to, why))
    n["state"], n["status_labels"] = to, ([] if to in TERMINAL else [to])
    n["note"] = why or None
    return "#%s: %s → %s" % (tid, old, to)


def pull_epics(tickets, tid, lines):
    """First active child pulls its parent chain to in-progress."""
    p = tickets[tid].get("parent")
    while p and p in tickets and tickets[p]["state"] in PULLABLE:
        lines.append(apply_state(tickets, p, "in-progress", "epic: child #%s active" % tid))
        p = tickets[p].get("parent")


def close_epics(tickets, p, lines):
    """An epic closes when every child is terminal and at least one is done
    (an all-wontfix epic stays a human call)."""
    while p and p in tickets:
        kids = children(tickets, p)
        if kids and tickets[p]["state"] not in TERMINAL \
           and all(tickets[k]["state"] in TERMINAL for k in kids) \
           and any(tickets[k]["state"] == "done" for k in kids):
            lines.append(apply_state(tickets, p, "done", "epic: all children terminal"))
            p = tickets[p].get("parent")
        else:
            break


def newly_eligible(tickets, done_tid):
    out = []
    for t in sorted(tickets, key=int):
        n = tickets[t]
        if n["state"] == "ready-for-agent" and done_tid in n["blocked_by"] \
           and all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"]):
            out.append("now eligible: #%s  %s" % (t, " ".join(n["title"].split())))
    return out
