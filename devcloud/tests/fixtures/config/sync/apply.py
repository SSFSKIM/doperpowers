"""The stand-in apply step: records that it ran, and as whom."""
import os
import pathlib
import time

state = pathlib.Path.home() / ".local/state/devcloud-test"
state.mkdir(parents=True, exist_ok=True)
with open(state / "apply.log", "a") as log:
    log.write(f"{os.getuid()} {time.time()}\n")
