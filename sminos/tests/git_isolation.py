"""The caller's repository kept out (#623): git's variables that select a
repository (`git rev-parse --local-env-vars`: GIT_DIR, GIT_WORK_TREE,
GIT_INDEX_FILE and the rest), which a hook or a git alias exports, removed
from this process's environment, so a fixture's `git init` makes the
repository it names and never initialises the caller's. Run first by
devcloud_isolation.py, and by the files run by themselves that do not run
that (the benches' rig, the live checks, rl10_conformance.py,
bridge_order.py); devcloud-isolation.sh does the same for the shell suites.
Proved by test_git_isolation.py."""
import os
import subprocess

for _var in subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True).stdout.split():
    os.environ.pop(_var, None)
