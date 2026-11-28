"""The suite's fixture: a temporary home with the stand-in `gh` first on
PATH, the stand-in `sminos` named by TASK_SMINOS, a GitHub state with one
board (acme/widgets) and helpers to seed issues, make clones and read the
log. Every name here is invented."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent / "bin" / "task"
STANDIN = HERE / "standin"

ME = "acme-owner"
OUTSIDER = "passer-by"
REPO = "acme/widgets"
SESSION = "11111111-aaaa-4bbb-8ccc-000000000001"
ADDRESS = "builder#11111111 (widgets on laptop)"
OTHER_SESSION = "33333333-aaaa-4bbb-8ccc-000000000003"
OTHER_ADDRESS = "fixer#33333333 (widgets on laptop)"
REVIEWER = {"thread": "44444444-aaaa-4bbb-8ccc-000000000004", "session": "22222222-aaaa-4bbb-8ccc-000000000002",
            "short": "22222222", "alias": "reviewer", "opened": "2026-11-20T00:00:00Z", "state": "idle",
            "ended": False, "local": True, "machine": "laptop", "project": {"id": "p-1", "name": "widgets"},
            "not_carried": ""}
REVIEWER_ADDRESS = "reviewer#22222222 (widgets on laptop)"
THREAD = "55555555-aaaa-4bbb-8ccc-000000000005"        # SESSION's thread
OTHER_THREAD = "66666666-aaaa-4bbb-8ccc-000000000006"  # OTHER_SESSION's thread


def thread_answer(thread, session, alias="builder", ended=False, local=True):
    """What `sminos who --thread=<name>` prints for a thread of this machine."""
    return {"thread": thread, "session": session, "short": session[:8], "alias": alias,
            "opened": "2026-11-20T00:00:00Z", "state": "idle", "ended": ended, "local": local, "machine": "laptop",
            "project": {"id": "p-1", "name": "widgets"}, "not_carried": ""}


def claim_body(holder=ADDRESS, attempt="0123456789abcdef"):
    return "```task-claim\nop: claim\nholder: %s\nattempt: %s\n```" % (holder, attempt)


def release_body(of, reason="released"):
    return "```task-claim\nop: release\nof: %d\nreason: %s\n```" % (of, reason)


def takeover_body(of, holder=OTHER_ADDRESS, attempt="fedcba9876543210", reason="forced: the owner said so"):
    return "```task-claim\nop: takeover\nholder: %s\nattempt: %s\nof: %d\nreason: %s\n```" % (
        holder, attempt, of, reason)


def board_file(binding="task", repo=REPO, **extra):
    data = {"binding": binding, "repo": repo}
    data.update(extra)
    return json.dumps(data)


class BoardCase(unittest.TestCase):
    """One fresh world per test."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="task-suite-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "gh").symlink_to(STANDIN / "gh")
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        self.gh_state = self.tmp / "gh.json"
        self.gh_log = self.tmp / "gh.log"
        self.sm_state = self.tmp / "sminos.json"
        self.sm_log = self.tmp / "sminos.log"
        self.state = {"login": ME, "clock": 0, "next_id": 9000, "fail": [], "repos": {}}
        self.add_repo(REPO)
        mine = thread_answer(THREAD, SESSION)
        other = thread_answer(OTHER_THREAD, OTHER_SESSION, alias="fixer")
        self.sminos = {"addresses": {SESSION: ADDRESS, OTHER_SESSION: OTHER_ADDRESS},
                       "threads": {"reviewer": REVIEWER, SESSION: mine, THREAD: mine, OTHER_SESSION: other,
                                   OTHER_THREAD: other},
                       "say": {"exit": 0}}
        self.save()

    # ── the GitHub state ──────────────────────────────────────────────────
    def save(self):
        self.gh_state.write_text(json.dumps(self.state))
        self.sm_state.write_text(json.dumps(self.sminos))

    def load(self):
        self.state = json.loads(self.gh_state.read_text())
        return self.state

    def add_repo(self, name, files=None, binding="task"):
        if files is None:
            files = {".doperpowers/board.json": board_file(binding, name)}
        self.state["repos"][name] = {"default_branch": "main", "files": files, "labels": {}, "next": 1,
                                     "issues": {}}

    def issue(self, n, title="a ticket", body="Something to do.", labels=(), repo=REPO, author=ME, editor=None,
              state="OPEN", reason="default", blocked_by=(), parent=None, comments=(), prs=(), branches=()):
        """An issue; a closed one is completed unless `reason` says otherwise (None: no reason, as GitHub gives for
        an old close)."""
        if reason == "default":
            reason = "COMPLETED" if state == "CLOSED" else None
        blocked = [[b[0], b[1]] if isinstance(b, (list, tuple)) else [repo, b] for b in blocked_by]
        self.state["repos"][repo]["issues"][str(n)] = {
            "number": n, "title": title, "body": body, "state": state, "stateReason": reason, "author": author,
            "editor": editor, "createdAt": "2026-10-01T00:00:00Z", "labels": list(labels),
            "blocked_by": blocked, "parent": [repo, parent] if isinstance(parent, int) else parent,
            "comments": list(comments), "prs": list(prs), "branches": list(branches)}
        self.state["repos"][repo]["next"] = max(self.state["repos"][repo]["next"], n + 1)
        self.save()

    def ticket(self, n, readiness="ready-to-work", horizon="expected", priority="P3", category="bug", **kw):
        labels = [l for l in (readiness, horizon, priority and "priority:" + priority, category) if l]
        labels += list(kw.pop("extra", ()))
        self.issue(n, labels=labels, **kw)

    def comment(self, n, body, cid, created="2026-11-02T00:00:00Z", author=ME, editor=None, repo=REPO):
        """A comment seeded on issue n."""
        self.state["repos"][repo]["issues"][str(n)]["comments"].append(
            {"id": cid, "author": author, "editor": editor, "createdAt": created, "body": body})
        self.save()

    def hook(self, match, do, when="before", stdin=None, times=1):
        """At the next `times` calls that match, the stand-in does `do` (its actions) before the call is served,
        or after."""
        self.load()
        h = {"match": match, "do": do, "when": when, "times": times}
        if stdin is not None:
            h["stdin"] = stdin
        self.state.setdefault("hooks", []).append(h)
        self.save()

    def index(self):
        p = self.tmp / "task-home" / "claims.json"
        return json.loads(p.read_text()) if p.exists() else {"v": 1, "settled": {}, "rows": []}

    def rows(self):
        return self.index()["rows"]

    def gh_issue(self, n, repo=REPO):
        return self.load()["repos"][repo]["issues"][str(n)]

    def fail_on(self, match, times=1, status=422, message="stand-in refusal", stdin=None, after=False):
        """The next `times` calls that match fail; `stdin` narrows the match to a call whose input holds it, and
        `after` carries the call out before it fails (a write accepted whose answer was never heard)."""
        self.load()  # what earlier commands wrote stays
        rule = {"match": match, "times": times, "status": status, "message": message, "after": after}
        if stdin is not None:
            rule["stdin"] = stdin
        self.state["fail"].append(rule)
        self.save()

    # ── running the CLI ───────────────────────────────────────────────────
    def env(self, session=SESSION):
        env = {"PATH": "%s:%s" % (self.bin, os.environ.get("PATH", "/usr/bin:/bin")), "HOME": str(self.home),
               "TASK_GH_STATE": str(self.gh_state), "TASK_GH_LOG": str(self.gh_log),
               "TASK_SMINOS": str(STANDIN / "sminos"), "TASK_SMINOS_STATE": str(self.sm_state),
               "TASK_SMINOS_LOG": str(self.sm_log), "TASK_HOME": str(self.tmp / "task-home"),
               "GIT_AUTHOR_NAME": "suite", "GIT_AUTHOR_EMAIL": "suite@example.invalid",
               "GIT_COMMITTER_NAME": "suite", "GIT_COMMITTER_EMAIL": "suite@example.invalid",
               "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C.UTF-8"}
        if session:
            env["CLAUDE_CODE_SESSION_ID"] = session
        return env

    def task(self, *args, cwd=None, session=SESSION, repo=True, env=None):
        """Run the CLI; `repo` adds `--repo acme/widgets` (a string names another)."""
        argv = [str(TASK)] + list(args)
        if repo:
            argv += ["--repo", REPO if repo is True else repo]
        e = self.env(session)
        if env:
            e.update(env)
        done = subprocess.run(argv, cwd=str(cwd or self.outside), env=e, capture_output=True, text=True,
                              timeout=60)
        self.load()  # what the command wrote, so that a later save() keeps it
        return done.returncode, done.stdout, done.stderr

    def json(self, *args, **kw):
        code, out, err = self.task(*(list(args) + ["--json"]), **kw)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def body_file(self, text):
        p = self.tmp / ("body-%d.md" % len(list(self.tmp.glob("body-*.md"))))
        p.write_text(text)
        return str(p)

    # ── the logs ──────────────────────────────────────────────────────────
    def calls(self):
        if not self.gh_log.exists():
            return []
        return [json.loads(line) for line in self.gh_log.read_text().splitlines()]

    def clear_log(self):
        for p in (self.gh_log, self.sm_log):
            if p.exists():
                p.unlink()

    def sminos_calls(self):
        if not self.sm_log.exists():
            return []
        return [json.loads(line)["argv"] for line in self.sm_log.read_text().splitlines()]

    @staticmethod
    def is_write(call):
        argv = call["argv"]
        if "graphql" in argv:
            return any("mutation " in a for a in argv)
        if "-X" in argv:
            return argv[argv.index("-X") + 1] != "GET"
        return call["stdin"] is not None

    def writes(self):
        return [c for c in self.calls() if self.is_write(c)]

    @staticmethod
    def path_of(call):
        """The path of a `gh api` call (`graphql` for a GraphQL one)."""
        argv = call["argv"]
        return next(a for i, a in enumerate(argv[1:], 1) if not a.startswith("-") and argv[i - 1] not in (
            "-X", "-f", "-F", "--input", "-H", "--hostname"))

    @classmethod
    def rest(cls, call):
        """(method, path, data) of a REST call."""
        argv = call["argv"]
        method = argv[argv.index("-X") + 1] if "-X" in argv else ("POST" if call["stdin"] else "GET")
        return method, cls.path_of(call), json.loads(call["stdin"]) if call["stdin"] else None

    def label_writes(self, n):
        out = []
        for c in self.writes():
            if "graphql" in c["argv"]:
                continue
            method, path, data = self.rest(c)
            if path == "repos/%s/issues/%d/labels" % (REPO, n) and method == "POST":
                out += [("+", l) for l in data["labels"]]
            elif path.startswith("repos/%s/issues/%d/labels/" % (REPO, n)) and method == "DELETE":
                out.append(("-", path.rsplit("/", 1)[1]))
            elif path == "repos/%s/issues/%d/labels" % (REPO, n):
                self.fail("a label write that is not a single add or remove: %s %s" % (method, path))
        return out

    # ── clones ────────────────────────────────────────────────────────────
    def git(self, cwd, *args, input=None):
        done = subprocess.run(["git"] + list(args), cwd=str(cwd), env=self.env(), capture_output=True, text=True,
                              input=input)
        if done.returncode != 0:
            raise AssertionError("git %s: %s" % (" ".join(args), done.stderr))
        return done.stdout.strip()

    NOREF = object()

    def clone(self, name="clone", remotes=None, defaults=None, worktree=None):
        """A clone whose remotes are `remotes` ({name: url}), whose remote-tracking default branch for each
        remote holds the board file `defaults[remote]` (None: no file; NOREF: no ref), and whose working tree
        holds `worktree` (None: no file). It makes no network call."""
        remotes = remotes or {"origin": "https://github.com/%s.git" % REPO}
        defaults = defaults if defaults is not None else {"origin": board_file()}
        path = self.tmp / name
        path.mkdir()
        self.git(path, "init", "-q", "-b", "work")
        for remote, url in remotes.items():
            self.git(path, "remote", "add", remote, url)
        for remote, text in defaults.items():
            if text is self.NOREF:
                continue
            index = self.tmp / ("index-%s-%s" % (name, remote))
            env = dict(self.env(), GIT_INDEX_FILE=str(index))
            if text is not None:
                blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=str(path), env=env, input=text,
                                      capture_output=True, text=True, check=True).stdout.strip()
                subprocess.run(["git", "update-index", "--add", "--cacheinfo",
                                "100644,%s,.doperpowers/board.json" % blob], cwd=str(path), env=env, check=True)
            tree = subprocess.run(["git", "write-tree"], cwd=str(path), env=env, capture_output=True, text=True,
                                  check=True).stdout.strip()
            commit = self.git(path, "commit-tree", tree, "-m", "default branch of %s" % remote)
            self.git(path, "update-ref", "refs/remotes/%s/main" % remote, commit)
            self.git(path, "symbolic-ref", "refs/remotes/%s/HEAD" % remote, "refs/remotes/%s/main" % remote)
        if worktree is not None:
            (path / ".doperpowers").mkdir()
            (path / ".doperpowers" / "board.json").write_text(worktree)
            self.git(path, "add", ".doperpowers/board.json")
        (path / "README").write_text("a clone\n")
        self.git(path, "add", "README")
        self.git(path, "commit", "-q", "-m", "work")
        return path
