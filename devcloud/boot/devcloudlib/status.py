"""`/var/lib/devcloud/status.json` (Interfaces I6): one entry per boot step,
`{"name", "state", "at", "detail"}`, kept in boot order whichever run wrote
it — a boot, a reconcile, or a job. `detail` never holds a value: callers
pass names, counts, exit codes and log paths only."""

import datetime
import json
import os
import pathlib
import tempfile

PATH = pathlib.Path("/var/lib/devcloud/status.json")

STEPS = (
    "identity",           # 1
    "seed",               # 2
    "bootstrap-secrets",  # 3
    "tailnet-attach",     # 4
    "configuration",      # 5
    "tailnet-check",      # 6
    "secrets",            # 7
    "home",               # 8
    "apply",              # 9
    "settings-and-env",   # 10
    "services",           # 11
    "projects",           # 12
)
STATES = ("ok", "failed", "skipped", "missing")


def load(path=PATH):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except FileNotFoundError:
        return {"steps": []}


def _write(data, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status.")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def reset(path=PATH):
    _write({"steps": []}, path)


def record(name, state, detail, path=PATH):
    if name not in STEPS:
        raise ValueError(f"unknown step {name!r}")
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = load(path)
    steps = {s["name"]: s for s in data.get("steps", [])}
    steps[name] = {"name": name, "state": state, "at": at, "detail": detail}
    data["steps"] = [steps[n] for n in STEPS if n in steps]
    _write(data, path)


def healthy(data):
    """Every step recorded, none failed."""
    steps = data.get("steps", [])
    return len(steps) == len(STEPS) and all(s["state"] != "failed" for s in steps)


def render(data):
    width = max(len(n) for n in STEPS)
    return "".join(f"{s['name']:<{width}}  {s['state']:<7}  {s['at']}  {s['detail']}\n"
                   for s in data.get("steps", []))
