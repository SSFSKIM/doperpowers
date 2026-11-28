"""All of the CLI's GitHub access, through `gh api` with the repository
named in every call (D4): no `gh issue`, no `{owner}` placeholder, nothing
that asks the client which repository a directory belongs to. It writes as
the account the client is authenticated as (D8's trusted account).

Label writes are single adds and removes, never a replacement of an issue's
label set, which would drop a label another writer set a moment before.
GraphQL operations are named `Task…`."""
import base64
import json
import re
import subprocess
import time
import urllib.parse

from common import failed

TIMEOUT = 120
# Every call names its host, so that GH_HOST or a client's default cannot send a read or a write elsewhere.
HOST = "github.com"

_ISSUE_FIELDS = """
  id number title url state stateReason createdAt body
  author { login } editor { login }
  labels(first: 50) { nodes { name } }
  blockedBy(first: 50) { nodes { number state stateReason repository { nameWithOwner } } }
  parent { number repository { nameWithOwner } }
  subIssues(first: 50) { nodes { number state stateReason repository { nameWithOwner } } }
  closedByPullRequestsReferences(first: 20, includeClosedPrs: true) { nodes { number state updatedAt url } }
  linkedBranches(first: 20) { nodes { ref { name target { ... on Commit { committedDate } } } } }
  timelineItems(itemTypes: [REOPENED_EVENT], last: 1) { nodes { ... on ReopenedEvent { createdAt } } }
"""
# A comment's id is read as fullDatabaseId: comment ids pass 2^31, beyond GraphQL's Int (databaseId).
_COMMENTS = """comments(first: 100%s) { pageInfo { hasNextPage endCursor }
  nodes { fullDatabaseId author { login } editor { login } createdAt body } }"""

Q_ISSUE = """query TaskIssue($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { issue(number: $number) { %s %s } } }""" % (_ISSUE_FIELDS, _COMMENTS % "")
Q_COMMENTS = """query TaskComments($owner: String!, $name: String!, $number: Int!, $cursor: String!) {
  repository(owner: $owner, name: $name) { issue(number: $number) { %s } } }""" % (_COMMENTS % ", after: $cursor")
Q_BOARD = """query TaskBoard($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 50, after: $cursor, states: [OPEN], orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor } nodes { %s %s } } } }""" % (_ISSUE_FIELDS, _COMMENTS % "")
SEARCH_PAGE = 100   # the most hits GitHub's search gives in one page
SEARCH_LIMIT = 1000  # and the furthest it reads: hits past the 1000th are never served
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
    """A call that failed. `status` is the HTTP status GitHub answered
    with, None when no answer was heard (a timeout, the transport)."""

    def __init__(self, message, not_found=False, status=None, body=""):
        super().__init__(message)
        self.message = message
        self.not_found = not_found
        self.status = status
        self.body = body  # what GitHub answered with, as gh printed it

    @property
    def refused(self):
        """GitHub answered, and refused: the write did not happen."""
        return self.status is not None and 400 <= self.status < 500


class OutOfTime(GitHubError):
    """A call not made, or cut short, because the bounded pass it belongs
    to (the settle before list or claim) reached its deadline."""


class Client:
    def __init__(self):
        self._login = None
        self._labels = {}
        # A time.monotonic() value that bounds every call while it is set (a settle's deadline).
        self.deadline = None

    # ── plumbing ──────────────────────────────────────────────────────────
    def _gh(self, args, data=None):
        argv = ["gh", "api", "--hostname", HOST] + args
        if data is not None:
            argv += ["--input", "-"]
        timeout, bounded = TIMEOUT, False
        if self.deadline is not None:
            left = self.deadline - time.monotonic()
            if left <= 0:
                raise OutOfTime("the pass ran out of time before gh api %s" % args[0])
            if left < timeout:
                timeout, bounded = left, True
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                  input=json.dumps(data) if data is not None else None)
        except FileNotFoundError:
            raise failed("the GitHub client `gh` is not installed: the board lives on GitHub")
        except subprocess.TimeoutExpired:
            if bounded:
                raise OutOfTime("the pass ran out of time during gh api %s" % args[0])
            raise GitHubError("gh api %s gave no answer within %d s" % (args[0], TIMEOUT))
        if done.returncode != 0:
            said = (done.stderr.strip() or done.stdout.strip() or "exit %d" % done.returncode).splitlines()
            message = said[-1] if said else "gh failed"
            status = re.search(r"\(HTTP (\d{3})\)", done.stderr)
            raise GitHubError(message, not_found="HTTP 404" in done.stderr or "NOT_FOUND" in done.stdout,
                              status=int(status.group(1)) if status else None, body=done.stdout)
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
            except OutOfTime:
                raise  # a bounded pass that ran out, not an authentication failure
            except GitHubError as e:
                raise failed("the GitHub client is not authenticated (gh api user: %s)" % e.message)
        return self._login

    def default_branch_file(self, repo, path):
        try:
            out = self.rest("GET", "repos/%s/contents/%s" % (repo, path))
        except OutOfTime:
            raise
        except GitHubError as e:
            if e.not_found:
                return None
            raise failed("%s's %s could not be read: %s" % (repo, path, e.message))
        if not isinstance(out, dict) or out.get("encoding") != "base64":
            return None
        try:
            return base64.b64decode(out["content"]).decode("utf-8")
        except ValueError:  # not base64, or not UTF-8: as unreadable as a file that is not JSON
            raise failed("%s's %s is not UTF-8 text: no board for task" % (repo, path))

    # ── reads ─────────────────────────────────────────────────────────────
    def issue(self, repo, number):
        """The issue with every comment, or GitHubError(not_found)."""
        owner, name = repo.split("/", 1)
        node = self.graphql_issue(Q_ISSUE, repo, number)
        self._read_on(owner, name, node, repo)
        return node

    @staticmethod
    def _gone(repo, number):
        return "%s has no issue #%d" % (repo, number)

    def _issue_of(self, data, repo, number):
        """The issue of an answer: one whose repository resolved and whose
        issue did not is gone (not_found); a repository that did not resolve
        is no such verdict."""
        if (data or {}).get("repository") is None:
            raise GitHubError("%s could not be read (no repository in GitHub's answer)" % repo)
        node = data["repository"]["issue"]
        if node is None:
            raise GitHubError(self._gone(repo, number), not_found=True)
        return node

    def graphql_issue(self, query, repo, number, **variables):
        """A query of one issue; GitHub's "Could not resolve to an Issue"
        (the repository resolved, the issue did not) is the issue gone."""
        owner, name = repo.split("/", 1)
        try:
            return self._issue_of(self.graphql(query, owner=owner, name=name, number=number, **variables), repo,
                                  number)
        except OutOfTime:
            raise
        except GitHubError as e:
            if e.not_found and e.message == self._gone(repo, number):
                raise
            if "Could not resolve to an Issue" in e.message:
                raise GitHubError(self._gone(repo, number), not_found=True)
            # Anything else, a repository this credential cannot see included, is not the issue gone.
            raise GitHubError(e.message, status=e.status, body=e.body)

    def _read_on(self, owner, name, node, repo=None):
        """Flatten the issue's first page of comments, reading on past it;
        each later page is judged as the first (`graphql_issue`)."""
        repo = repo or "%s/%s" % (owner, name)
        page = node["comments"]
        comments = list(page["nodes"])
        while page["pageInfo"]["hasNextPage"]:
            page = self.graphql_issue(Q_COMMENTS, repo, node["number"],
                                      cursor=page["pageInfo"]["endCursor"])["comments"]
            comments += page["nodes"]
        node["comments"] = comments

    def open_issues(self, repo):
        """The open issues, each with every comment: one paged query, and a
        read on for an issue with more comments than its page holds."""
        owner, name = repo.split("/", 1)
        nodes, cursor = [], None
        while True:
            page = self.graphql(Q_BOARD, owner=owner, name=name, cursor=cursor)["repository"]["issues"]
            for node in page["nodes"]:
                self._read_on(owner, name, node)
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
        """The board's hits, read a page at a time up to GitHub's search limit,
        and what was not read: {"unread": hits the search counted past the
        pages read, "incomplete": GitHub's search stopped short}."""
        q = "%s repo:%s is:issue" % (query, repo)
        if state in ("open", "closed"):
            q += " is:%s" % state
        items, counted, incomplete = {}, 0, False
        for page in range(1, SEARCH_LIMIT // SEARCH_PAGE + 1):
            out = self.rest("GET", "search/issues", params={"q": q, "per_page": str(SEARCH_PAGE), "page": str(page)})
            got = out.get("items", [])
            counted = max(counted, out.get("total_count", 0))
            incomplete = incomplete or bool(out.get("incomplete_results"))
            for h in got:  # a hit that moved between two pages is read once
                items.setdefault(((h.get("repository_url") or "").lower(), h["number"]), h)
            if len(got) < SEARCH_PAGE or len(items) >= counted:
                break
        home = "https://api.github.com/repos/%s" % repo.lower()
        # A query may name another repository of its own (`repo:` twice is an OR): only this board's hits count.
        hits = [h for h in items.values()
                if (h.get("repository_url") or "").lower() == home and "pull_request" not in h]
        return hits, {"unread": max(counted - len(items), 0), "incomplete": incomplete}

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
                try:
                    self.rest("POST", "repos/%s/labels" % repo,
                              {"name": name, "color": color, "description": description})
                except GitHubError as e:
                    # Another writer made it a moment ago (several sessions claim at once): GitHub says so.
                    if not (e.status == 422 and '"already_exists"' in e.body):
                        raise
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

    def delete_comment(self, repo, comment_id):
        """Delete a comment; one already gone is no failure."""
        try:
            self.rest("DELETE", "repos/%s/issues/comments/%d" % (repo, comment_id))
        except GitHubError as e:
            if not e.not_found:
                raise

    def add_blocked_by(self, issue_id, blocker_id):
        self.graphql(M_ADD_BLOCKED_BY, issue=issue_id, blocker=blocker_id)

    def remove_blocked_by(self, issue_id, blocker_id):
        self.graphql(M_REMOVE_BLOCKED_BY, issue=issue_id, blocker=blocker_id)

    def set_parent(self, parent_id, child_id):
        self.graphql(M_ADD_SUB_ISSUE, parent=parent_id, child=child_id, replace=True)

    def remove_parent(self, parent_id, child_id):
        self.graphql(M_REMOVE_SUB_ISSUE, parent=parent_id, child=child_id)
