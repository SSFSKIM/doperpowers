"""A fixture's git never reaches the repository the tests were started from
(#623): _path, which every unit test imports first, removes git's variables
that select a repository, so a fixture's `git init` makes the repository it
names. A child whose GIT_DIR and GIT_WORK_TREE name a decoy (a linked
worktree of a repository in a temporary directory) runs test_driver_keys's
`git` helper to make one; the decoy's files are checked byte for byte."""
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import _path  # noqa: F401

UNIT = pathlib.Path(__file__).resolve().parent
FIXTURE = """import sys
sys.path.insert(0, sys.argv[1])
import test_driver_keys
test_driver_keys.git(sys.argv[2], "init", "-q")
"""


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def tree(root):
    """{path: sha256} of every file under root."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in pathlib.Path(root).rglob("*") if p.is_file()}


class Decoy(unittest.TestCase):
    def test_fixture_leaves_the_callers_repository(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-git-")).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        decoy, wt, work = tmp / "decoy", tmp / "wt", tmp / "scratch" / "work"
        git("init", "-q", str(decoy))
        git("commit", "-q", "--allow-empty", "-m", "one", cwd=decoy)
        git("worktree", "add", "-q", str(wt), cwd=decoy)
        before = tree(decoy / ".git")
        work.mkdir(parents=True)
        env = dict(os.environ, GIT_DIR=str(decoy / ".git" / "worktrees" / "wt"), GIT_WORK_TREE=str(wt))
        r = subprocess.run([sys.executable, "-B", "-c", FIXTURE, str(UNIT), str(work)], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        after = tree(decoy / ".git")
        self.assertEqual(sorted(p for p in set(after) | set(before) if after.get(p) != before.get(p)), [],
                         "files of the decoy's repository changed")
        self.assertEqual(git("config", "core.bare", cwd=wt), "false")
        self.assertEqual(git("rev-parse", "--absolute-git-dir", cwd=work), str(work / ".git"))


if __name__ == "__main__":
    unittest.main()
