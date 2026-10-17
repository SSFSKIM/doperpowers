#!/usr/bin/env python3
"""The stand-in sminos CLI, in a stand-in doperpowers marketplace clone: what
boot step 11 relies on, and nothing else. `daemon install` writes the
systemd user unit as the real one does (it loads nothing); `daemon run`, the
unit's program, records its environment and waits."""
import json
import os
import pathlib
import sys
import time

home = pathlib.Path.home()
state = home / ".local/state/devcloud-test"

if sys.argv[1:] == ["daemon", "install"]:
    config = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    unit = pathlib.Path(config) / "systemd/user/sminos-daemon.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text("[Unit]\nDescription=stand-in sminos daemon\n\n[Service]\n"
                    f"ExecStart={sys.executable} {os.path.realpath(__file__)} daemon run\nRestart=always\n"
                    f'Environment="PATH={os.environ.get("PATH", "")}"\n\n[Install]\nWantedBy=default.target\n')
    unit.chmod(0o600)
    print(f"wrote {unit}")
elif sys.argv[1:] == ["daemon", "run"]:
    state.mkdir(parents=True, exist_ok=True)
    keys = ("SESSION_MIRROR_HOST", "DEVCLOUD_PROBE_PROFILE", "PATH")
    (state / "sminos.json").write_text(json.dumps({**{k: os.environ.get(k) for k in keys}, "pid": os.getpid()}))
    while True:
        time.sleep(60)
else:
    sys.exit(f"stand-in sminos: {' '.join(sys.argv[1:])} is not played here")
