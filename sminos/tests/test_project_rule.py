#!/usr/bin/env python3
"""A linked worktree's walk under design §8's rule (sminos.decision), as the
rule's author ruled it: a .smns on the worktree's own path is one below the
first folder the worktree shares with its main checkout R; files and stored
statements on the shared folders are weighed by the rule at R, the nearer
deciding. Pinned here until MAWS's project-rule.json version 2 carries the
case and its sync replaces this file. Hermetic: HOME and SMINOS_HOME are
temporary, the tree is git's files written directly, no git run.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
T = os.path.realpath(tempfile.mkdtemp(prefix="smrule."))
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"))
for k in ("CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(T, "s", "daemon"))
os.makedirs(os.path.join(T, "home"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts"))
import sminos  # noqa: E402

ORG, MACHINE = "org-rule", "rule-mac"
MINTED, FILED = "11111111-1111-4111-8111-111111111111", "55555555-5555-4555-8555-555555555555"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def repo(d):
    """A main checkout at `d` with no remote."""
    for sub in ("objects", "refs/heads"):
        os.makedirs(os.path.join(d, ".git", sub), exist_ok=True)
    write(os.path.join(d, ".git", "HEAD"), "ref: refs/heads/main\n")
    write(os.path.join(d, ".git", "config"), "[core]\n\tbare = false\n")


def worktree(wt, main):
    """A linked worktree of `main` at `wt`, as git lays it out."""
    admin = os.path.join(main, ".git", "worktrees", os.path.basename(wt))
    write(os.path.join(admin, "gitdir"), os.path.join(wt, ".git") + "\n")
    write(os.path.join(admin, "commondir"), "../..\n")
    write(os.path.join(admin, "HEAD"), "ref: refs/heads/%s\n" % os.path.basename(wt))
    write(os.path.join(wt, ".git"), "gitdir: %s\n" % admin)
    os.makedirs(os.path.join(wt, "src"), exist_ok=True)


def keep_org(at):
    org = {"projects": [], "machines": [], "at": ""}
    if at is not None:
        org["locations"] = {"gen": 1, "at": at}
    sminos.write_json(sminos.org_path(), org)
    sminos.forget_caches()


def minted(path, pid):
    st = os.stat(path)
    birth = sminos.birth_ns(getattr(st, "st_birthtime", 0))
    return {"path": sminos.canonical(path), "project": pid, "stated": "minted",
            "anchor": {"dev": str(st.st_dev), "ino": str(st.st_ino), "birth": str(int(birth or 0))}}


class SharedFolders(unittest.TestCase):
    """R = top/f/repo with no remote, f minted, top/.smns: a worktree inside
    the repository and one at top/elsewhere/wt are both f's minted project,
    where a whole upward walk from the second would reach top's file."""

    @classmethod
    def setUpClass(cls):
        sminos.write_json(os.path.join(T, "s", "daemon", "identity.json"),
                          {"org": ORG, "hub": "http://127.0.0.1:9", "name": MACHINE, "former": {}})
        cls.top = os.path.join(T, "top")
        cls.f, cls.r = os.path.join(cls.top, "f"), os.path.join(cls.top, "f", "repo")
        repo(cls.r)
        write(os.path.join(cls.top, ".smns"), json.dumps({"project": FILED, "name": "filed", "remote": ""}))
        cls.inside = os.path.join(cls.r, ".claude", "worktrees", "wt")
        cls.outside = os.path.join(cls.top, "elsewhere", "wt")
        worktree(cls.inside, cls.r)
        worktree(cls.outside, cls.r)

    def asked(self, d):
        got = sminos.decision(d)
        return got.project.id if got.project else None, got.by, got.at

    def test_both_worktrees_are_the_minted_folders(self):
        keep_org([minted(self.f, MINTED)])
        for wt in (self.inside, self.outside):
            for d in (wt, os.path.join(wt, "src")):
                self.assertEqual(self.asked(d), (MINTED, "minted", self.f), d)
        self.assertEqual(self.asked(self.r), (MINTED, "minted", self.f), "as its main checkout is")

    def test_with_no_statement_both_take_the_file_above_the_checkout(self):
        for at in (None, []):
            keep_org(at)
            for wt in (self.inside, self.outside):
                self.assertEqual(self.asked(wt), (FILED, "smns", self.top), "%s, locations %r" % (wt, at))


def git_dir(d, url):
    """A git directory at `d` (not a checkout's `.git` beside it) with remote `url`."""
    for sub in ("objects", "refs/heads"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    write(os.path.join(d, "HEAD"), "ref: refs/heads/main\n")
    write(os.path.join(d, "config"), '[core]\n\tbare = false\n[remote "origin"]\n\turl = %s\n' % url)


def smns(d, pid):
    write(os.path.join(d, ".smns"), json.dumps({"project": pid, "name": pid[:4], "remote": ""}))


class NotAWorktree(unittest.TestCase):
    """A `.git` file is a linked worktree only where its gitdir holds a
    `commondir`: a checkout whose git dir lives elsewhere, and a submodule,
    are their own repository's project, as before the rule, with or without
    `locations` kept."""

    @classmethod
    def setUpClass(cls):
        sminos.write_json(os.path.join(T, "s", "daemon", "identity.json"),
                          {"org": ORG, "hub": "http://127.0.0.1:9", "name": MACHINE, "former": {}})

    def each_mode(self, d, want, label):
        for at in (None, []):
            keep_org(at)
            got = sminos.decision(d)
            self.assertEqual((got.project.id if got.project else None, got.by), want, "%s, locations %r" % (label, at))

    def test_a_separate_git_dir_is_its_own_repositorys(self):
        outer = os.path.join(T, "sep", "outer")
        git_dir(os.path.join(outer, "storage", ".git"), "https://github.com/example/sep.git")
        smns(outer, FILED)   # beside the git dir, never above the checkout
        checkout = os.path.join(T, "sep", "checkout")
        write(os.path.join(checkout, ".git"), "gitdir: %s\n" % os.path.join(outer, "storage", ".git"))
        self.each_mode(checkout, (sminos.repo_project_id(ORG, "github.com/example/sep"), "remote"),
                       "a --separate-git-dir checkout")

    def test_a_submodule_is_its_own_repositorys(self):
        sup = os.path.join(T, "sub", "super")
        git_dir(os.path.join(sup, ".git"), "https://github.com/example/super.git")
        git_dir(os.path.join(sup, ".git", "modules", "m"), "https://github.com/example/m.git")
        write(os.path.join(sup, "m", ".git"), "gitdir: ../.git/modules/m\n")
        self.each_mode(os.path.join(sup, "m"), (sminos.repo_project_id(ORG, "github.com/example/m"), "remote"),
                       "a submodule")


class EmptyLocations(unittest.TestCase):
    """`locations` kept puts the rule over canonical paths whatever it
    holds: a session launched through a symlink, its alias and real sides
    under different .smns files, is the same project with an empty `at` and
    with one statement on a folder elsewhere."""

    def test_an_unrelated_statement_moves_no_session(self):
        sminos.write_json(os.path.join(T, "s", "daemon", "identity.json"),
                          {"org": ORG, "hub": "http://127.0.0.1:9", "name": MACHINE, "former": {}})
        real, alias = os.path.join(T, "sym", "real"), os.path.join(T, "sym", "alias")
        os.makedirs(os.path.join(real, "x"))
        os.makedirs(alias)
        smns(real, FILED)
        smns(alias, MINTED)
        os.symlink(os.path.join(real, "x"), os.path.join(alias, "link"))
        elsewhere = os.path.join(T, "sym", "elsewhere")
        os.makedirs(elsewhere)
        cwd = os.path.join(alias, "link")
        keep_org([])
        empty = sminos.decision(cwd)
        keep_org([minted(elsewhere, "22222222-2222-4222-8222-222222222222")])
        one = sminos.decision(cwd)
        self.assertEqual((empty.project.id, empty.at), (FILED, os.path.realpath(real)), "an empty `at`: the real side")
        self.assertEqual((one.project.id, one.at), (empty.project.id, empty.at), "one statement elsewhere: the same")
        keep_org(None)
        self.assertEqual(sminos.decision(cwd).project.id, MINTED, "no `locations`: the path as given, as before")


def tearDownModule():
    shutil.rmtree(T, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
