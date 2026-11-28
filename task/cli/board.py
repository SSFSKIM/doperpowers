"""The board's vocabulary (D1, Interfaces §2) and a ticket as the reading
verbs give it (Interfaces §5): its axes read from its labels, its record
read from a trusted body (D8), and whether a session may take it on its own
initiative, the first condition being that the fold of its claim records
(claims.py) names no holder."""
import claims
import record

READINESS = ("ready-to-work", "need-design", "need-input")
HORIZONS = ("planned", "expected", "undecided")
PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_PREFIX = "priority:"
CATEGORIES = ("bug", "enhancement", "spike", "env-issue")
CLAIMED = "claimed"
BATCH_PREFIX = "batch:"
STATUS_PREFIX = "status:"

# Whether a blocked-by edge may name an issue of another repository (`owner/name#n`). Delegated unknowns: settled
# by `task/tests/live.sh edge`; if GitHub refuses such an edge, set this False and such a wait is prose in the body.
CROSS_REPOSITORY_BLOCKED_BY = True

# What a label is created with at its first need: a color and a description that names its axis.
_AXIS = {
    "readiness": ("0e8a16", "task board readiness: what must exist before work can start"),
    "horizon": ("5319e7", "task board horizon: how far off the work is"),
    "priority": ("d93f0b", "task board priority"),
    "category": ("1d76db", "task board category"),
    "batch": ("fbca04", "task board batch: a named set one agent takes whole"),
    "claim": ("c5def5", "task board claim: a thread holds it (its claim records decide; the label shows them)"),
}


def label_spec(name):
    """(color, description) for a label of the board's vocabulary."""
    if name in READINESS:
        return _AXIS["readiness"]
    if name in HORIZONS:
        return _AXIS["horizon"]
    if name.startswith(PRIORITY_PREFIX):
        return _AXIS["priority"]
    if name in CATEGORIES:
        return _AXIS["category"]
    if name.startswith(BATCH_PREFIX):
        return _AXIS["batch"]
    if name == CLAIMED:
        return _AXIS["claim"]
    raise KeyError(name)


def readiness_of(labels):
    return [l for l in labels if l in READINESS]


def horizons_of(labels):
    return [l for l in labels if l in HORIZONS]


def priorities_of(labels):
    return [l for l in labels if l.startswith(PRIORITY_PREFIX)]


def categories_of(labels):
    return [l for l in labels if l in CATEGORIES]


def batches_of(labels):
    return [l for l in labels if l.startswith(BATCH_PREFIX)]


def statuses_of(labels):
    return [l for l in labels if l.startswith(STATUS_PREFIX)]


def _one(values):
    return values[0] if len(values) == 1 else None


def _repo_of(node):
    return node["repository"]["nameWithOwner"]


def issue_state(node):
    """(state, close_reason) of §5: open with null, or closed with
    `completed`, `not-planned` (a duplicate is not planned) or null, for a
    close whose reason this does not know. A close GitHub gives no reason
    for is completed (D1): those come from before GitHub had close reasons,
    when "not planned" did not exist."""
    if node["state"] == "OPEN":
        return "open", None
    reason = node.get("stateReason")
    if reason in ("COMPLETED", None):
        return "closed", "completed"
    if reason in ("NOT_PLANNED", "DUPLICATE"):
        return "closed", "not-planned"
    return "closed", None


def ref_state(node):
    """A blocker's or a child's §5 state: `open`, `completed`,
    `not-planned`, or `closed` when its close reason is unknown."""
    state, reason = issue_state(node)
    return reason or state


# A blocker in one of these states is not known to be completed: the ticket is stuck.
STUCK = ("not-planned", "closed")


def trusted(node, login):
    """D8: authored by the trusted account, and last edited, if at all, by it."""
    author = (node.get("author") or {}).get("login")
    editor = (node.get("editor") or {}).get("login")
    return author == login and (editor is None or editor == login)


def _login(actor):
    return (actor or {}).get("login")


class Ticket:
    """One issue read through the board's rules."""

    def __init__(self, repo, node, login):
        self.repo, self.node, self.login = repo, node, login
        self.number = node["number"]
        self.labels = [l["name"] for l in node["labels"]["nodes"]]
        self.state, self.close_reason = issue_state(node)
        self.body = node.get("body") or ""
        self.body_trusted = trusted(node, login)
        self.parsed = record.parse(self.body)
        self.blockers = [{"repo": _repo_of(b), "number": b["number"], "state": ref_state(b)}
                         for b in node["blockedBy"]["nodes"]]
        reopened = ((node.get("timelineItems") or {}).get("nodes") or [{}])[-1].get("createdAt")
        self.fold = claims.Fold(claims.records(node.get("comments") or [], lambda c: trusted(c, login)),
                                self.state == "open", reopened)

    @property
    def holder(self):
        """The record that holds the ticket, by the fold; None when unheld."""
        return self.fold.holder

    @property
    def label_agrees(self):
        """Whether `claimed` shows what the fold says (off a closed ticket)."""
        return (CLAIMED in self.labels) == (self.holder is not None)

    @property
    def on_board(self):
        """D1: an open issue is on the board when it carries a readiness label."""
        return self.state == "open" and bool(readiness_of(self.labels))

    @property
    def record_values(self):
        """§5's `record`: null when the body is not trusted or its block
        cannot be read; else every key, null where absent."""
        if not self.body_trusted or not self.parsed.readable:
            return None
        return self.parsed.values()

    def not_takeable(self, caller_address):
        """The reasons of §5's `not_takeable`, D1's conditions in order;
        `caller_address()` is asked only when a `for:` must be compared."""
        reasons = []
        if self.state != "open":
            reasons.append("closed")
        if self.holder is not None:
            reasons.append("held")
        if readiness_of(self.labels) != ["ready-to-work"]:
            reasons.append("readiness")
        horizons = horizons_of(self.labels)
        if len(horizons) != 1 or horizons[0] not in ("expected", "planned"):
            reasons.append("horizon")
        if any(b["state"] == "open" for b in self.blockers):
            reasons.append("blocked")
        if any(b["state"] in STUCK for b in self.blockers):
            reasons.append("stuck")
        if horizons == ["planned"] and not self.blockers:
            reasons.append("planned-without-blocker")
        if not self.body_trusted:
            reasons.append("untrusted-body")
        elif not self.parsed.readable:
            # Its `for:` cannot be read, and anything unknown counts against.
            reasons.append("malformed-record")
        else:
            wanted = self.parsed.fields.get("for")
            if wanted and wanted != caller_address():
                reasons.append("for-another")
        return reasons

    @property
    def linked(self):
        """The pull requests and branches GitHub links to the ticket, with
        their last activity: what lets a reader judge a quiet claim."""
        n = self.node
        out = [{"kind": "pr", "number": p["number"], "state": p["state"].lower(), "updated": p["updatedAt"],
                "url": p["url"]} for p in n["closedByPullRequestsReferences"]["nodes"]]
        for b in n["linkedBranches"]["nodes"]:
            ref = b.get("ref")
            if ref:
                out.append({"kind": "branch", "name": ref["name"],
                            "updated": (ref.get("target") or {}).get("committedDate")})
        return out

    def view(self, caller_address, full=True):
        """The object of Interfaces §5 (`list` drops `body` and `comments`)."""
        n = self.node
        reasons = self.not_takeable(caller_address)
        linked = self.linked
        priority = _one(priorities_of(self.labels))
        batch = _one(batches_of(self.labels))
        out = {
            "repo": self.repo, "number": self.number, "url": n["url"], "title": n["title"],
            "state": self.state, "close_reason": self.close_reason, "on_board": self.on_board,
            "readiness": _one(readiness_of(self.labels)), "horizon": _one(horizons_of(self.labels)),
            "priority": priority[len(PRIORITY_PREFIX):] if priority else None,
            "category": _one(categories_of(self.labels)),
            "batch": batch[len(BATCH_PREFIX):] if batch else None,
            "labels": self.labels,
            "author": _login(n.get("author")), "editor": _login(n.get("editor")),
            "body_trusted": self.body_trusted, "body_digest": record.digest(self.body),
            "record": self.record_values,
            "blocked_by": self.blockers,
            "parent": {"repo": _repo_of(n["parent"]), "number": n["parent"]["number"]} if n.get("parent") else None,
            "children": [{"repo": _repo_of(c), "number": c["number"], "state": ref_state(c)}
                         for c in n["subIssues"]["nodes"]],
            "holder": ({"address": self.holder.holder, "claim": self.holder.id, "since": self.holder.created}
                       if self.holder else None),
            "linked": linked,
            "takeable": not reasons, "not_takeable": reasons,
        }
        if full:
            out["body"] = self.body
            out["comments"] = [{"id": int(c["fullDatabaseId"]), "author": _login(c.get("author")),
                                "trusted": trusted(c, self.login), "created": c["createdAt"], "body": c["body"]}
                               for c in n.get("comments", [])]
        return out
