"""`task migrate plan` and `task migrate apply` (D6, Interfaces §8): the
one-time relabel of a board from the old `status:*` vocabulary, by a plan
a session reads before it is applied.

The plan reads the open issues and proposes, for each, the readiness and
horizon the old label decides, or a decision row where it does not. The
apply writes what was reviewed onto what was read, or nothing: each row's
issue is read again, and only a state the write order (body; horizon on;
readiness on; old status labels off) can leave is taken up and finished.
Anything else is skipped and named for a new plan."""
import datetime
import json
import os
import pathlib
import subprocess

import board as B
import config
import legacy
import record
from common import failed, refused, usage
from github import GitHubError

BY_RULE = None  # a horizon the rule decides: planned with an open blocker, else expected
FALLBACK = ("need-design", "undecided")  # keeps a session from building it on its own initiative

# An old status label -> (readiness, horizon, the question a decision row puts; None for a mechanical row).
MAPPING = {
    "status:ready-for-implementer": ("ready-to-work", BY_RULE, None),
    "status:ready-for-agent": ("ready-to-work", BY_RULE, None),
    "status:ready-for-architect": ("need-design", BY_RULE, None),
    "status:interactive-preferred": ("need-design", BY_RULE, None),
    "status:needs-human": ("need-input", BY_RULE, None),
    "status:needs-info": ("need-input", BY_RULE, None),
    "status:blocked": ("need-input", BY_RULE, None),
    "status:deferred": FALLBACK + ("deferred has no mechanical target: read it for its readiness, and for "
                                   "whether it will be done (expected, planned) or that is open (undecided)",),
    "status:in-design": ("need-design", BY_RULE, "in design: is a session still on it? If so it is asked to "
                         "claim it after the apply; else it returns to the backlog"),
    "status:in-progress": ("ready-to-work", BY_RULE, "in progress: is a session still on it? If so it is asked "
                           "to claim it after the apply; else it returns to the backlog"),
    "status:in-review": ("ready-to-work", BY_RULE, "in review: is a session still on it? If so it is asked to "
                         "claim it after the apply; else it returns to the backlog"),
    "status:confident-ready": ("ready-to-work", BY_RULE, "confident-ready: is a session still on it? If so it is "
                               "asked to claim it after the apply; else it returns to the backlog"),
}
TWO_STATUSES = "two status labels: read it for its readiness and horizon"
UNKNOWN_STATUS = "a status label the mapping does not know: read it for its readiness and horizon"
NO_STATUS = ("no status label: read it for its readiness and horizon, or leave it untracked (action \"leave\")")
ACTIONS = ("relabel", "body", "leave")
BOARD_AXES = B.READINESS + B.HORIZONS


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _board_labels(labels):
    """The labels the relabel compares: the old status labels, the readiness and the horizon."""
    return {l for l in labels if l.startswith(B.STATUS_PREFIX) or l in BOARD_AXES}


def _blockers(ticket):
    return sorted(({"repo": b["repo"], "number": b["number"], "state": b["state"]} for b in ticket.blockers),
                  key=lambda b: (b["repo"].lower(), b["number"]))


def _blocker_key(blockers):
    return sorted((b["repo"].lower(), b["number"], b["state"]) for b in blockers)


# ── plan ──────────────────────────────────────────────────────────────────
def _one(values):
    return values[0] if len(values) == 1 else None


def _row(ticket, login):
    """The plan's row for one open issue, "incoming", or None (no row)."""
    labels = ticket.labels
    statuses = B.statuses_of(labels)
    author = (ticket.node.get("author") or {}).get("login")
    seen = {"state": "open", "labels": labels, "body": record.digest(ticket.body),
            "body_trusted": ticket.body_trusted, "blockers": _blockers(ticket)}
    body_after = legacy.rewrite(ticket.body) if ticket.body_trusted else None
    row = {"number": ticket.number, "title": ticket.node["title"], "seen": seen, "action": "relabel",
           "readiness": None, "horizon": None, "basis": "mechanical", "decided": True, "why": "",
           "body_after": body_after}
    if not statuses:
        if B.readiness_of(labels):
            if body_after is None:
                return None
            # On the board already: its body alone is rewritten, its labels stay as seen.
            row.update(action="body", readiness=_one(B.readiness_of(labels)), horizon=_one(B.horizons_of(labels)))
            return row
        if author != login:
            return "incoming"
        readiness, horizon, question = FALLBACK + (NO_STATUS,)
    elif len(statuses) > 1:
        readiness, horizon, question = FALLBACK + (TWO_STATUSES,)
    else:
        readiness, horizon, question = MAPPING.get(statuses[0], FALLBACK + (UNKNOWN_STATUS,))
    if horizon is BY_RULE:
        horizon = "planned" if any(b["state"] == "open" for b in ticket.blockers) else "expected"
    row.update(readiness=readiness, horizon=horizon)
    if question is not None:
        row.update(basis="decision", decided=False, question=question)
    return row


def _inside_a_work_tree(directory):
    try:
        done = subprocess.run(["git", "-C", str(directory), "rev-parse", "--show-toplevel"], capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _plan_path(out, repo):
    if out is not None:
        path = pathlib.Path(out).expanduser().resolve()
    else:
        home = pathlib.Path(os.environ.get("TASK_HOME") or pathlib.Path.home() / ".claude" / "task")
        stamp = _now().replace(":", "").replace("-", "")
        path = home.resolve() / "plans" / ("%s-%s.json" % (repo.replace("/", "-"), stamp))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tree = _inside_a_work_tree(path.parent)
    if tree is not None:
        raise usage("%s is inside the work tree %s: a plan is written outside every repository's tree, so that it "
                    "is never committed (give --out a path elsewhere)" % (path, tree))
    return path


def _write_private(path, text):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(text)


def plan(ctx):
    a = ctx.args
    if a.repo is not None:
        if not config.valid_repo(a.repo):
            raise usage("--repo takes owner/name, not %r" % a.repo)
        repo = a.repo
    else:
        repo = config.clone_repository(os.getcwd())
    path = _plan_path(a.out, repo)
    try:
        nodes = ctx.client.open_issues(repo)
    except GitHubError as e:
        raise failed(e.message)
    login = ctx.client.login()
    rows, incoming = [], []
    for node in sorted(nodes, key=lambda n: n["number"]):
        row = _row(B.Ticket(repo, node, login), login)
        if row == "incoming":
            incoming.append(node["number"])
        elif row is not None:
            rows.append(row)
    data = {"v": 1, "repo": repo, "read_at": _now(), "rows": rows, "incoming": incoming}
    _write_private(path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    decisions = [r for r in rows if r["basis"] == "decision"]
    lines = ["plan: %s" % path,
             "%s: %d rows: %d mechanical, %d decisions; incoming: %d%s"
             % (repo, len(rows), len(rows) - len(decisions), len(decisions), len(incoming),
                " (%s)" % ", ".join("#%d" % n for n in incoming) if incoming else "")]
    rewritten = [r["number"] for r in rows if r["body_after"] is not None]
    if rewritten:
        lines.append("bodies rewritten (read each row's body_after): %s" % ", ".join("#%d" % n for n in rewritten))
    if decisions:
        lines.append("decisions, each to settle in the plan (action, readiness, horizon, why, decided: true):")
        for r in decisions:
            old = ", ".join(B.statuses_of(r["seen"]["labels"])) or "no status label"
            lines.append("  #%d %s [%s] fallback %s/%s: %s" % (r["number"], r["title"], old, r["readiness"],
                                                              r["horizon"], r["question"]))
    print("\n".join(lines))


# ── apply ─────────────────────────────────────────────────────────────────
def _load_plan(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise usage("the plan %s cannot be read: %s" % (path, e.strerror))
    except ValueError:
        raise usage("the plan %s is not JSON" % path)
    if not isinstance(data, dict) or data.get("v") != 1 or not isinstance(data.get("rows"), list) \
            or not isinstance(data.get("repo"), str):
        raise usage("%s is no plan of task migrate plan (v 1, a repo and rows)" % path)
    for r in data["rows"]:
        problem = _row_problem(r)
        if problem:
            raise usage("the plan's row %s %s" % (r.get("number", "?") if isinstance(r, dict) else "?", problem))
    return data


def _row_problem(r):
    if not isinstance(r, dict) or not isinstance(r.get("number"), int):
        return "is no row (a number is required)"
    if not r.get("decided"):
        return None  # refused as undecided, after the plan is known to be this board's
    if r.get("action") not in ACTIONS:
        return "has the action %r: one of %s" % (r.get("action"), ", ".join(ACTIONS))
    if not isinstance(r.get("seen"), dict) and r["action"] != "leave":
        return "has no seen"
    if r["action"] == "relabel" and (r.get("readiness") not in B.READINESS or r.get("horizon") not in B.HORIZONS):
        return "relabels to %r and %r: a readiness (%s) and a horizon (%s)" % (
            r.get("readiness"), r.get("horizon"), ", ".join(B.READINESS), ", ".join(B.HORIZONS))
    if r.get("body_after") is not None and not isinstance(r["body_after"], str):
        return "has a body_after that is no text"
    return None


def _ops(row, seen_labels):
    """The label writes of a relabel row in D6's order, from the labels as
    seen: the horizon on and the other horizons off, the readiness on and
    the other readiness labels off, then the old status labels off."""
    ops = []
    for wanted, axis in ((row["horizon"], B.HORIZONS), (row["readiness"], B.READINESS)):
        if wanted not in seen_labels:
            ops.append(("+", wanted))
        ops += [("-", l) for l in sorted(seen_labels) if l in axis and l != wanted]
    ops += [("-", l) for l in sorted(seen_labels) if l.startswith(B.STATUS_PREFIX)]
    return ops


def _on_the_path(row, seen_labels, now):
    """Whether the board labels `now` are a state the label writes leave,
    from the labels as seen: each axis in its turn, a later axis untouched
    until the earlier is set, an old label taken off in any order."""
    if row["action"] != "relabel":
        return now == seen_labels
    h, r = row["horizon"], row["readiness"]
    statuses = {l for l in seen_labels if l.startswith(B.STATUS_PREFIX)}
    seen_h = {l for l in seen_labels if l in B.HORIZONS}
    seen_r = {l for l in seen_labels if l in B.READINESS}
    now_h = {l for l in now if l in B.HORIZONS}
    now_r = {l for l in now if l in B.READINESS}
    now_s = {l for l in now if l.startswith(B.STATUS_PREFIX)}
    if now - seen_labels - {h, r}:
        return False
    horizon_set = now_h == {h}
    readiness_set = now_r == {r}
    if not horizon_set:  # the horizon in its turn: what was seen, with h on and some others off
        return (now_h == seen_h or (h in now_h and now_h <= seen_h | {h})) and now_r == seen_r and now_s == statuses
    if not readiness_set:
        return (now_r == seen_r or (r in now_r and now_r <= seen_r | {r})) and now_s == statuses
    return now_s <= statuses


def _target_labels(row, seen_labels):
    if row["action"] == "relabel":
        return {row["horizon"], row["readiness"]}
    return seen_labels


def _differs(row, seen, ticket, now_labels, seen_labels, target_body, rewrites):
    """What makes the issue no state of the plan's own row, or None."""
    if ticket.state != "open":
        return "the issue is closed"
    if _blocker_key(ticket.blockers) != _blocker_key(seen.get("blockers") or []):
        return "its blockers moved (seen %s, now %s)" % (_refs(seen.get("blockers") or []), _refs(ticket.blockers))
    digest = record.digest(ticket.body)
    if digest == seen.get("body"):
        if rewrites and now_labels != seen_labels:
            return ("its labels moved over the body as read (seen %s, now %s): the order leaves no such state, so "
                    "it is someone's edit since" % (_labels(seen_labels), _labels(now_labels)))
    elif not (rewrites and digest == record.digest(target_body)):
        return "its body was edited since the plan (its digest is now %s)" % digest
    if not _on_the_path(row, seen_labels, now_labels):
        return "a board label moved (seen %s, now %s)" % (_labels(seen_labels), _labels(now_labels))
    return None


def _refs(blockers):
    return ", ".join("%s#%d %s" % (b["repo"], b["number"], b["state"]) for b in blockers) or "none"


def _labels(labels):
    return ", ".join(sorted(labels)) or "none"


class Apply:
    def __init__(self, ctx):
        self.client, self.repo = ctx.client, ctx.repo
        self.writes = 0
        self.lines, self.skipped, self.failed = [], [], []
        self.counts = {"relabelled": 0, "rewritten": 0, "done already": 0, "left": 0}

    def row(self, row, login):
        n = row["number"]
        if row["action"] == "leave":
            self.counts["left"] += 1
            return
        seen = row["seen"]
        seen_labels = _board_labels(seen.get("labels") or [])
        rewrites = row.get("body_after") is not None
        try:
            node = self.client.issue(self.repo, n)
        except GitHubError as e:
            if e.not_found:
                return self.skip(n, "the issue is not there (%s)" % e.message)
            return self.fail(n, e.message, "reading it")
        ticket = B.Ticket(self.repo, node, login)
        now_labels = _board_labels(ticket.labels)
        target_labels = _target_labels(row, seen_labels)
        target_body = row["body_after"] if rewrites else None
        target_body_digest = record.digest(target_body) if rewrites else seen.get("body")
        digest = record.digest(ticket.body)
        if digest == target_body_digest and now_labels == target_labels:
            self.counts["done already"] += 1
            return
        why = _differs(row, seen, ticket, now_labels, seen_labels, target_body, rewrites)
        if why:
            return self.skip(n, why)
        done = []
        try:
            if rewrites and digest != target_body_digest:
                if not ticket.body_trusted:
                    return self.skip(n, "its body is no longer trusted (last edited by %s): no body is written "
                                     "that is not trusted" % ((node.get("editor") or {}).get("login") or "unknown"))
                self.write(done, "its body", self.client.edit_issue, self.repo, n, body=target_body)
            if row["action"] == "relabel":
                self.ensure([l for l in (row["horizon"], row["readiness"]) if l not in now_labels])
                have = set(now_labels)
                for op, label in _ops(row, seen_labels):
                    if op == "+" and label not in have:
                        self.write(done, "+" + label, self.client.add_label, self.repo, n, label)
                        have.add(label)
                    elif op == "-" and label in have:
                        self.write(done, "-" + label, self.client.remove_label, self.repo, n, label)
                        have.discard(label)
        except GitHubError as e:
            return self.fail(n, e.message, "after %s" % (", ".join(done) or "no write"))
        if row["action"] == "relabel":
            self.counts["relabelled"] += 1
        if "its body" in done:
            self.counts["rewritten"] += 1
        self.lines.append("#%d %s: %s" % (n, row["action"] if row["action"] == "body" else "relabelled",
                                          ", ".join(done) or "nothing left to write"))

    def ensure(self, labels):
        if labels:
            self.client.ensure_labels(self.repo, {l: B.label_spec(l) for l in labels})

    def write(self, done, what, call, *args, **kw):
        self.writes += 1
        call(*args, **kw)
        done.append(what)

    def skip(self, n, why):
        self.skipped.append(n)
        self.lines.append("#%d skipped: %s" % (n, why))

    def fail(self, n, said, where):
        self.failed.append(n)
        self.lines.append("#%d failed %s: %s (run the apply again: it finishes the row from where it stands)"
                          % (n, where, said))


def apply(ctx):
    a = ctx.args
    data = _load_plan(a.plan)
    repo = ctx.repo  # the board, binding "task" on its default branch, before anything else is read
    if data["repo"].lower() != repo.lower():
        raise failed("the plan %s was made for %s, and this board is %s: a plan is applied only to the board it "
                     "read" % (a.plan, data["repo"], repo))
    open_rows = [r for r in data["rows"] if not r.get("decided")]
    if open_rows:
        raise refused("%d decision row%s of the plan %s not settled (set action, readiness, horizon, why and "
                      "decided: true): %s; nothing was written"
                      % (len(open_rows), " is" if len(open_rows) == 1 else "s are", a.plan,
                         ", ".join("#%d" % r["number"] for r in open_rows)))
    login = ctx.client.login()
    run = Apply(ctx)
    for row in sorted(data["rows"], key=lambda r: r["number"]):
        run.row(row, login)
    try:
        still = [n["number"] for n in ctx.client.open_issues(repo)
                 if B.statuses_of([l["name"] for l in n["labels"]["nodes"]])]
        still_text = ", ".join("#%d" % n for n in sorted(still)) or "none"
    except GitHubError as e:
        still_text = "unknown (the board could not be read: %s)" % e.message
        run.failed.append(None)
    c = run.counts
    out = run.lines + [
        "relabelled %d, bodies rewritten %d, done already %d, left %d, skipped %d, failed %d; writes: %d"
        % (c["relabelled"], c["rewritten"], c["done already"], c["left"], len(run.skipped),
           len([f for f in run.failed if f is not None]), run.writes),
        "still carrying an old status label: %s" % still_text]
    if run.skipped:
        out.append("skipped, for a new plan: %s" % ", ".join("#%d" % n for n in run.skipped))
    print("\n".join(out))
    if run.failed:
        raise failed("the apply stopped short: run it again, and it finishes each row from where it stands")
