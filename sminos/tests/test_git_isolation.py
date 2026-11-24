#!/usr/bin/env python3
"""A fixture's git never reaches the repository the tests were started from
(#623). A run started where git exported its repository variables (a hook,
`git -c alias.x='!…' x`) passed them to every fixture's `git init`, which then
initialised the caller's repository: from a linked worktree, `core.bare =
true` and `core.worktree` written into its shared config. What every runnable
test file runs first removes them: git_isolation.py (from devcloud_isolation.py
for the Python test files, directly in the files run by themselves that do not
run that), devcloud-isolation.sh for the shell suites.

Each case starts an entry point's preamble and a fixture that makes a
repository in a child whose GIT_DIR and GIT_WORK_TREE name a decoy (a linked
worktree of a repository in a temporary directory), then checks the decoy's
files byte for byte and the scratch repository where the fixture put it.
Run: python3 -B sminos/tests/test_git_isolation.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
# The fixture of test_threads.py (and of the suites built on it, the channels'
# roster among them): Machine.repo, a `git init` of a directory under its home.
PY_FIXTURE = """import sys
sys.path.insert(0, sys.argv[1])
import test_threads
m = object.__new__(test_threads.Machine)
m.home = sys.argv[2]
m.repo("work")
"""
# A file run directly that runs git_isolation.py itself (rl10_conformance.py, bridge_order.py, the benches' rig,
# the live checks), then its own `git init`.
DIRECT_FIXTURE = """import os, runpy, subprocess, sys
runpy.run_path(os.path.join(sys.argv[1], "git_isolation.py"))
subprocess.run(["git", "init", "-q", os.path.join(sys.argv[2], "work")], check=True)
"""
# A shell suite: the preamble sourced, then its own `git init`.
SH_FIXTURE = '. "$1/devcloud-isolation.sh"; git init -q "$2/work"'


def git(*args, cwd=None):
    """The test's own git, under none of the caller's configuration (a signing commit.gpgSign among it)."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def tree(root):
    """{path: sha256} of every file under root."""
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class Decoy(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="smgit."))
        self.addCleanup(shutil.rmtree, self.tmp)
        decoy = os.path.join(self.tmp, "decoy")
        git("init", "-q", decoy)
        git("commit", "-q", "--allow-empty", "-m", "one", cwd=decoy)
        self.wt = os.path.join(self.tmp, "wt")
        git("worktree", "add", "-q", self.wt, cwd=decoy)
        self.common = os.path.join(decoy, ".git")
        self.before = tree(self.common)
        self.scratch = os.path.join(self.tmp, "scratch")
        os.mkdir(self.scratch)
        # The caller's environment: git's variables naming the decoy's worktree.
        self.env = dict(os.environ, GIT_DIR=os.path.join(self.common, "worktrees", "wt"), GIT_WORK_TREE=self.wt,
                        TMPDIR=self.tmp)

    def check(self, argv):
        r = subprocess.run(argv, env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        after = tree(self.common)
        self.assertEqual(sorted(p for p in set(after) | set(self.before) if after.get(p) != self.before.get(p)), [],
                         "files of the decoy's repository changed")
        self.assertEqual(git("config", "core.bare", cwd=self.wt), "false")
        work = os.path.join(self.scratch, "work")
        self.assertEqual(git("rev-parse", "--absolute-git-dir", cwd=work), os.path.join(work, ".git"))

    def test_python_fixture(self):
        self.check([sys.executable, "-B", "-c", PY_FIXTURE, HERE, self.scratch])

    def test_direct_preamble(self):
        self.check([sys.executable, "-B", "-c", DIRECT_FIXTURE, HERE, self.scratch])

    def test_shell_suite(self):
        self.check(["bash", "-c", SH_FIXTURE, "_", HERE, self.scratch])


if __name__ == "__main__":
    unittest.main()
