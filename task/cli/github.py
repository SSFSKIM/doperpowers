"""All of the CLI's GitHub access, through `gh api` with the repository
named in every call (D4): no `gh issue`, no `{owner}` placeholder, nothing
that asks the client which repository a directory belongs to. It writes as
the account the client is authenticated as (D8's trusted account).

Label writes are single adds and removes, never a replacement of an issue's
label set, which would drop a label another writer set a moment before."""
import base64
import json
import subprocess
import urllib.parse

from common import failed

TIMEOUT = 120

_ISSUE_FIELDS = """
  id number title url state stateReason createdAt body
  author { login } editor { login }
  labels(first: 50) { nodes { name } }
  blockedBy(first: 50) { nodes { number state stateReason repository { nameWithOwner } } }
  parent { number repository { nameWithOwner } }
  subIssues(first: 50) { nodes { number state stateReason repository { nameWithOwner } } }
  closedByPullRequestsReferences(first: 20, includeClosedPrs: true) { nodes { number state updatedAt url } }
  linkedBranches(first: 20) { nodes { ref { name target { ... on Commit { committedDate } } } } }
"""
_COMMENTS = """comments(first: 100%s) { pageInfo { hasNextPage endCursor }
  nodes { fullDatabaseId author { login } editor { login } createdAt body } }"""

Q_ISSUE = """query TaskIssue($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { issue(number: $number) { %s %s } } }""" % (_ISSUE_FIELDS, _COMMENTS % "")
Q_COMMENTS = """query TaskComments($owner: String!, $name: String!, $number: Int!, $cursor: String!) {
  repository(owner: $owner, name: $name) { issue(number: $number) { %s } } }""" % (_COMMENTS % ", after: $cursor")
Q_BOARD = """query TaskBoard($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 50, after: $cursor, states: [OPEN], orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor } nodes { %s } } } }""" % _ISSUE_FIELDS
Q_NODE = """query TaskIssueNode($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { issue(number: $number) {
    id number state stateReason
    blockedBy(first: 50) { nodes { number repository { nameWithOwner } } } } } }"""
M_ADD_BLOCKED_BY = """mutation TaskAddBlockedBy($issue: ID!, $blocker: ID!) {
  addBlockedBy(input: {issueId: $issue, blockingIssueId: $blocker}) { issue { number } } }"""
M_REMOVE_BLOCKED_BY = """mutation TaskRemoveBlockedBy($issue: ID!, $blocker: ID!) {
  removeBlockedBy(input: {issueId: $issue, blockingIssueId: $blocker}) { issue { number } } }"""
M_ADD_SUB_ISSUE = """mutation TaskAddSubIssue($parent: ID!, $child: ID!, $replace: Boolean) {
  addSubIssue(input: {issueId: $parent, subIssueId: $child, replaceParent: $replace}) { issue { number } } }"""
M_REMOVE_SUB_ISSUE = """mutation TaskRemoveSubIssue($parent: ID!, $child: ID!) {
  removeSubIssue(input: {issueId: $parent, subIssueId: $child}) { issue { number } } }"""


class GitHubError(Exception):
    def __init__(self, message, not_found=False):
        super().__init__(message)
        self.message = message
        self.not_found = not_found


class Client:
    def __init__(self):
        self._login = None
        self._labels = {}

    # ── plumbing ──────────────────────────────────────────────────────────
    def _gh(self, args, data=None):
        argv = ["gh", "api"] + args
        if data is not None:
            argv += ["--input", "-"]
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT,
                                  input=json.dumps(data) if data is not None else None)
        except FileNotFoundError:
            raise failed("the GitHub client `gh` is not installed: the board lives on GitHub")
        except subprocess.TimeoutExpired:
            raise GitHubError("gh api %s gave no answer within %d s" % (args[0], TIMEOUT))
        if done.returncode != 0:
            said = (done.stderr.strip() or done.stdout.strip() or "exit %d" % done.returncode).splitlines()
            message = said[-1] if said else "gh failed"
            raise GitHubError(message, not_found="HTTP 404" in done.stderr or "NOT_FOUND" in done.stdout)
        try:
            return json.loads(done.stdout) if done.stdout.strip() else None
        except ValueError:
            raise GitHubError("gh api %s answered no JSON" % args[0])

    def rest(self, method, path, data=None, params=None):
        args = [path, "-X", method]
        for k, v in (params or {}).items():
            args += ["-f", "%s=%s" % (k, v)]
        return self._gh(args, data)

    def graphql(self, query, **variables):
        args = ["graphql", "-f", "query=%s" % query]
        for k, v in variables.items():
            if v is None:
                continue
            if isinstance(v, bool):
                args += ["-F", "%s=%s" % (k, "true" if v else "false")]
            elif isinstance(v, int):
                args += ["-F", "%s=%d" % (k, v)]
            else:
                args += ["-f", "%s=%s" % (k, v)]
        out = self._gh(args)
        if out.get("errors"):
            raise GitHubError("; ".join(e.get("message", "?") for e in out["errors"]))
        return out["data"]

    # ── the account and the configuration ─────────────────────────────────
    def login(self):
        """The trusted account (D8): the login the client is authenticated
        as, read once per run."""
        if self._login is None:
            try:
                self._login = self.rest("GET", "user")["login"]
            except GitHubError as e:
                raise failed("the GitHub client is not authenticated (gh api user: %s)" % e.message)
        return self._login

    def default_branch_file(self, repo, path):
        try:
            out = self.rest("GET", "repos/%s/contents/%s" % (repo, path))
        except GitHubError as e:
            if e.not_found:
                return None
            raise failed("%s's %s could not be read: %s" % (repo, path, e.message))
        if not isinstance(out, dict) or out.get("encoding") != "base64":
            return None
        return base64.b64decode(out["content"]).decode("utf-8")

    # ── reads ─────────────────────────────────────────────────────────────
    def issue(self, repo, number):
        """The issue with every comment, or GitHubError(not_found)."""
        owner, name = repo.split("/", 1)
        try:
            node = self.graphql(Q_ISSUE, owner=owner, name=name, number=number)["repository"]["issue"]
        except GitHubError as e:
            if "Could not resolve to an Issue" in e.message:
                raise GitHubError("%s has no issue #%d" % (repo, number), not_found=True)
            raise
        if node is None:
            raise GitHubError("%s has no issue #%d" % (repo, number), not_found=True)
        page = node["comments"]
        comments = list(page["nodes"])
        while page["pageInfo"]["hasNextPage"]:
            page = self.graphql(Q_COMMENTS, owner=owner, name=name, number=number,
                                cursor=page["pageInfo"]["endCursor"])["repository"]["issue"]["comments"]
            comments += page["nodes"]
        node["comments"] = comments
        return node

    def open_issues(self, repo):
        owner, name = repo.split("/", 1)
        nodes, cursor = [], None
        while True:
            page = self.graphql(Q_BOARD, owner=owner, name=name, cursor=cursor)["repository"]["issues"]
            nodes += page["nodes"]
            if not page["pageInfo"]["hasNextPage"]:
                return nodes
            cursor = page["pageInfo"]["endCursor"]

    def issue_node(self, repo, number):
        """id, state and blockers of an issue, in any repository; None when
        there is no such issue."""
        owner, name = repo.split("/", 1)
        try:
            return self.graphql(Q_NODE, owner=owner, name=name, number=number)["repository"]["issue"]
        except GitHubError as e:
            if e.not_found or "Could not resolve" in e.message:
                return None
            raise

    def search(self, repo, query, state):
        q = "%s repo:%s is:issue" % (query, repo)
        if state in ("open", "closed"):
            q += " is:%s" % state
        out = self.rest("GET", "search/issues", params={"q": q, "per_page": "100"})
        home = "https://api.github.com/repos/%s" % repo.lower()
        # A query may name another repository of its own (`repo:` twice is an OR): only this board's hits count.
        return [h for h in out.get("items", [])
                if (h.get("repository_url") or "").lower() == home and "pull_request" not in h]

    # ── labels ────────────────────────────────────────────────────────────
    def ensure_labels(self, repo, wanted):
        """Create each label of `wanted` ({name: (color, description)}) that
        the repository lacks: a label is made at its first need."""
        if repo not in self._labels:
            pages = self._gh(["repos/%s/labels" % repo, "-X", "GET", "-f", "per_page=100", "--paginate",
                              "--slurp"])
            self._labels[repo] = {l["name"] for page in pages or [] for l in page or []}
        for name, (color, description) in wanted.items():
            if name not in self._labels[repo]:
                self.rest("POST", "repos/%s/labels" % repo,
                          {"name": name, "color": color, "description": description})
                self._labels[repo].add(name)

    def add_label(self, repo, number, label):
        self.rest("POST", "repos/%s/issues/%d/labels" % (repo, number), {"labels": [label]})

    def remove_label(self, repo, number, label):
        try:
            self.rest("DELETE", "repos/%s/issues/%d/labels/%s" % (repo, number, urllib.parse.quote(label, safe="")))
        except GitHubError as e:
            if not e.not_found:  # already off
                raise

    # ── issue writes ──────────────────────────────────────────────────────
    def create_issue(self, repo, title, body, labels):
        return self.rest("POST", "repos/%s/issues" % repo, {"title": title, "body": body, "labels": labels})

    def edit_issue(self, repo, number, **fields):
        return self.rest("PATCH", "repos/%s/issues/%d" % (repo, number), fields)

    def comment(self, repo, number, body):
        return self.rest("POST", "repos/%s/issues/%d/comments" % (repo, number), {"body": body})

    def add_blocked_by(self, issue_id, blocker_id):
        self.graphql(M_ADD_BLOCKED_BY, issue=issue_id, blocker=blocker_id)

    def remove_blocked_by(self, issue_id, blocker_id):
        self.graphql(M_REMOVE_BLOCKED_BY, issue=issue_id, blocker=blocker_id)

    def set_parent(self, parent_id, child_id):
        self.graphql(M_ADD_SUB_ISSUE, parent=parent_id, child=child_id, replace=True)

    def remove_parent(self, parent_id, child_id):
        self.graphql(M_REMOVE_SUB_ISSUE, parent=parent_id, child=child_id)
