"""The stand-in apply step: records that it ran, and as whom, and links devenv."""
import os
import pathlib
import time

state = pathlib.Path.home() / ".local/state/devcloud-test"
state.mkdir(parents=True, exist_ok=True)
with open(state / "apply.log", "a") as log:
    log.write(f"{os.getuid()} {time.time()}\n")

# The devenv link boot step 12 calls, as the real apply step makes it.
link = pathlib.Path.home() / ".local/bin/devenv"
link.parent.mkdir(parents=True, exist_ok=True)
if not link.is_symlink():
    link.symlink_to(pathlib.Path.home() / ".claude/tools/devenv")
