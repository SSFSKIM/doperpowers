"""Puts devcloud/boot on the import path, where devcloudlib lives, and devcloud/
itself, where the driver package lives.

And keeps the caller's repository out (#623): git's variables that select a
repository (`git rev-parse --local-env-vars`: GIT_DIR, GIT_WORK_TREE and the
rest), which a hook or a git alias exports, are removed, so a fixture's git
acts on the repository it names (test_git_isolation.py)."""
import os
import pathlib
import subprocess
import sys

DEVCLOUD = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DEVCLOUD / "boot"))
sys.path.insert(0, str(DEVCLOUD))
for _var in subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True).stdout.split():
    os.environ.pop(_var, None)
