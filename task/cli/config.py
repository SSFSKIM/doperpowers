"""Which board a command works, and whether `task` may work it (D4,
Interfaces §1).

In a clone the board is the repository of the designated remote (`git
config task.remote`, else `origin`), read from the remote's URL; its
configuration is `.doperpowers/board.json` on that remote's default branch
as the clone last fetched it, never the working tree's copy. Under `--repo`
it is the named repository and its default branch on GitHub. Nothing here
asks the GitHub client which repository a directory belongs to, and nothing
fetches."""
import json
import re
import shlex
import subprocess

from common import failed, usage

FILE = ".doperpowers/board.json"
_REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+")
_URL_FORMS = (
    re.compile(r"https://github\.com/(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?"),
    re.compile(r"git@github\.com:(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?"),
    re.compile(r"ssh://git@github\.com/(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?"),
)


def valid_repo(name):
    return bool(_REPO.fullmatch(name or "")) and not name.endswith(".git")


def repo_from_url(url):
    """owner/name from a remote URL in a form git writes for a GitHub
    repository; None for anything else."""
    for form in _URL_FORMS:
        m = form.fullmatch(url.strip())
        if m and valid_repo(m.group("repo")):
            return m.group("repo")
    return None


class Board:
    """The board a command works: `repo` (owner/name, as the remote or
    `--repo` spells it) and where its configuration was read (`source`)."""

    def __init__(self, repo, source):
        self.repo, self.source = repo, source

    @property
    def owner(self):
        return self.repo.split("/", 1)[0]

    @property
    def name(self):
        return self.repo.split("/", 1)[1]


def _git(cwd, *args):
    try:
        done = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise failed("git %s could not run: %s" % (" ".join(args), e))
    except UnicodeDecodeError:
        raise failed("git %s gave text that is not UTF-8" % " ".join(args))
    return done.returncode, done.stdout, done.stderr


def _check(text, repo, source):
    """The configuration's verdict: a Board, or the refusal naming where it
    was read and what it found there. No key but `binding` and `repo` is
    read."""
    try:
        data = json.loads(text)
    except ValueError:
        raise failed("%s is not JSON: no board for task" % source)
    if not isinstance(data, dict):
        raise failed("%s is not a JSON object: no board for task" % source)
    named = data.get("repo")
    if not isinstance(named, str) or not named:
        raise failed("%s names no repo: no board for task" % source)
    if named.lower() != repo.lower():
        raise failed("%s names %s, but it was read for %s: task works only the board of the repository its "
                     "configuration was read for" % (source, named, repo))
    binding = data.get("binding")
    if binding != "task":
        raise failed("%s says binding %s, not \"task\": this board is not worked by task (the old board scripts "
                     "own it until its default branch says \"task\")" % (source, json.dumps(binding)))
    return Board(repo, source)


def _designated(cwd):
    """(remote, repository) of the clone's designated remote."""
    code, out, _ = _git(cwd, "rev-parse", "--git-dir")
    if code != 0:
        raise failed("this directory is in no git clone: run task from a clone of the board's repository, or name "
                     "the board with --repo owner/name")
    code, out, _ = _git(cwd, "config", "--get", "task.remote")
    remote = out.strip() if code == 0 and out.strip() else "origin"
    code, out, _ = _git(cwd, "remote", "get-url", remote)
    if code != 0:
        raise failed("this clone has no remote %r (the designated remote: `git config task.remote`, else origin)"
                     % remote)
    url = out.strip()
    repo = repo_from_url(url)
    if repo is None:
        raise failed("remote %s's URL %s is no GitHub repository: no board for task" % (remote, url))
    return remote, repo


def clone_repository(cwd):
    """The repository of the clone's designated remote, its configuration
    unread: what `task migrate plan` needs, which runs before a board has
    moved."""
    return _designated(cwd)[1]


def from_clone(cwd):
    remote, repo = _designated(cwd)
    ref = "refs/remotes/%s/HEAD" % remote
    # That exact ref, never a revision lookup that a branch or tag spelled the same could answer.
    code, out, _ = _git(cwd, "show-ref", "--verify", "--hash", ref)
    commit = out.strip()
    if code != 0 or not commit:
        raise failed("this clone has no %s, so remote %s's default branch is not known here: run `git remote "
                     "set-head %s --auto` (task makes no fetch of its own)" % (ref, remote, shlex.quote(remote)))
    source = "%s:%s" % (ref, FILE)
    code, out, _ = _git(cwd, "show", "%s:%s" % (commit, FILE))
    if code != 0:
        raise failed("%s holds no %s: the default branch of %s, as this clone last fetched it, gives task no "
                     "board" % (ref, FILE, repo))
    return _check(out, repo, source)


def from_github(repo, client):
    if not valid_repo(repo):
        raise usage("--repo takes owner/name, not %r" % repo)
    source = "%s's default branch:%s" % (repo, FILE)
    text = client.default_branch_file(repo, FILE)
    if text is None:
        raise failed("%s's default branch holds no %s: no board for task" % (repo, FILE))
    return _check(text, repo, source)
