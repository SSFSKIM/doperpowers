"""`/var/lib/devcloud/status.json` (Interfaces I6): one entry per boot step,
`{"name", "state", "at", "detail"}`, kept in boot order whichever run wrote
it — a boot, a reconcile, or a job. `detail` never holds a value: callers
pass names, counts, exit codes and log paths only.

Beside the steps, two records a boot's reset keeps, since they outlive a
reboot: `lifecycle`, the departure or release once one has started (§4.2:
`{"op", "state", "at", "detail", "steps": [...]}`, state `departing`, `held`
or `departed`), and `enroll`, a deferred enrollment (§10: `{"state":
"deferred", "since"}`), cleared once the desk has decided."""

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
# deferred: step 11's enrollment waits on an undecided desk, which counts as ok.
STATES = ("ok", "failed", "skipped", "missing", "deferred")
# Once a departure has started, admission stays closed: the periodic jobs exit
# at once, `lease set` refuses, and a boot starts no daemon (§4.1, §4.2).
DEPARTURE_STARTED = ("departing", "held", "departed")
LIFECYCLE_STATES = DEPARTURE_STARTED


def load(path=None):
    try:
        return json.loads(pathlib.Path(path or PATH).read_text())
    except FileNotFoundError:
        return {"steps": []}


def _write(data, path):
    path = pathlib.Path(path or PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status.")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reset(path=None):
    """A boot starts its steps from nothing; the lifecycle and a deferred
    enrollment stay."""
    data = load(path)
    _write({"steps": [], **{k: data[k] for k in ("lifecycle", "enroll") if k in data}}, path)


def record(name, state, detail, path=None):
    if name not in STEPS:
        raise ValueError(f"unknown step {name!r}")
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    data = load(path)
    steps = {s["name"]: s for s in data.get("steps", [])}
    steps[name] = {"name": name, "state": state, "at": now(), "detail": detail}
    data["steps"] = [steps[n] for n in STEPS if n in steps]
    _write(data, path)


def lifecycle(path=None):
    """The departure's or release's record, or None before one started."""
    return load(path).get("lifecycle")


def departure_started(path=None):
    record = lifecycle(path)
    return record is not None and record.get("state") in DEPARTURE_STARTED


def release_started(path=None):
    """Whether a release has started on this adopted machine (§6.5): from
    then on nothing configures it again, since each boot step would undo a
    step the release did (the firewall, the keys, the tailnet)."""
    record = lifecycle(path)
    return record is not None and record.get("op") == "release" and record.get("state") in DEPARTURE_STARTED


def set_lifecycle(op, state, detail, steps=None, path=None):
    """Records the departure (`op` depart) or release (`op` release) as
    `state`; `steps` replaces the record's step outcomes when given."""
    if state not in LIFECYCLE_STATES:
        raise ValueError(f"unknown lifecycle state {state!r}")
    data = load(path)
    previous = data.get("lifecycle") or {}
    data["lifecycle"] = {"op": op, "state": state, "at": now(), "detail": detail,
                         "steps": steps if steps is not None else previous.get("steps", [])}
    _write(data, path)


def enroll_deferred(path=None):
    """When the enrollment was first deferred, or None."""
    record = load(path).get("enroll")
    return record.get("since") if record and record.get("state") == "deferred" else None


def set_enroll_deferred(deferred, path=None):
    """Marks the enrollment deferred (keeping the first deferral's time) or
    decided (the record removed)."""
    data = load(path)
    if deferred:
        data["enroll"] = {"state": "deferred", "since": enroll_deferred(path) or now()}
    else:
        data.pop("enroll", None)
    _write(data, path)


def healthy(data):
    """Every step recorded, none failed."""
    steps = data.get("steps", [])
    return len(steps) == len(STEPS) and all(s["state"] != "failed" for s in steps)


def render(data):
    width = max(len(n) for n in STEPS)
    out = "".join(f"{s['name']:<{width}}  {s['state']:<7}  {s['at']}  {s['detail']}\n"
                  for s in data.get("steps", []))
    enroll = data.get("enroll")
    if enroll and enroll.get("state") == "deferred":
        out += f"enroll deferred since {enroll['since']}\n"
    record = data.get("lifecycle")
    if record:
        out += f"{record['op']:<{width}}  {record['state']:<7}  {record['at']}  {record['detail']}\n"
    return out
