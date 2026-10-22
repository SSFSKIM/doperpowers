"""The kind of a host's tailnet node (the driver's Design §4.1): ephemeral
while the host has a lease, non-ephemeral while it is kept, at every change
of the lease and not only at the first join.

No status or netmap field shows whether a node is ephemeral (M1), so the
join records the kind it asked for, and a node whose recorded kind is not the
one its lease wants is rejoined: the boot's tailnet attach does it, and so
does the `devcloud-rejoin` transient unit that a lease write changing the
kind starts (the lease service starts it again while the kind stays behind).
Only a node joined with the OAuth client can be rejoined: a fallback auth key
file is deleted once used."""

import json
import pathlib
import time

from . import proc

PATH = pathlib.Path("/var/lib/devcloud/tailnet.json")
UNIT = "devcloud-rejoin"
JOINED, REJOINING, FAILED = "joined", "rejoining", "failed"


def wanted(d):
    """The kind `d`'s lease wants: True for ephemeral."""
    return d.leased


def applies(d):
    return d.tailscale == "join" and bool(d.ts_secret)


def name(ephemeral):
    return "ephemeral" if ephemeral else "non-ephemeral"


def recorded(path=None):
    """{ephemeral, wanted, state, detail, name, at}, or {} before the first
    join recorded one. `ephemeral` is the kind of the node last joined; None
    once a rejoin logged it out and did not join again. `name` is the one the
    tailnet gave the node, which is the host's unless an older node held it."""
    try:
        data = json.loads(pathlib.Path(path or PATH).read_text())
    except (FileNotFoundError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(ephemeral, wanted_kind, state, detail="", name=None, path=None, now=time.time):
    data = {"ephemeral": ephemeral, "wanted": wanted_kind, "state": state, "detail": detail, "name": name,
            "at": int(now())}
    proc.write_file(pathlib.Path(path or PATH), json.dumps(data) + "\n", mode=0o644, dir_mode=0o755)


def behind(d, path=None):
    """Whether `d`'s node must be rejoined: an OAuth node not recorded as
    joined with the kind its lease wants (an unknown kind counts as behind)."""
    if not applies(d):
        return False
    data = recorded(path)
    return data.get("state") != JOINED or data.get("ephemeral") is not wanted(d)
