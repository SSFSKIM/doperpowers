#!/usr/bin/env python3
"""The retired path of the sminos CLI, kept while machines move to the sminos plugin.

sminos was a skill of doperpowers, its CLI here; it is now a plugin of its own,
sminos@doperpowers, whose folder is sminos/ at this repository's root. A daemon
service installed before the move names this path, and so does a devcloud
image older than the move (its boot looks for it), so this file goes on
answering: it finds the real CLI and runs it with the same arguments — the
sibling sminos/ folder first (the same repository: a checkout, the doperpowers
plugin cache, which copies the whole repository, and the marketplace clone a
daemon runs from), then the installed sminos plugin's — and does nothing else.
Each forward says so on stderr, so a daemon's log shows the hop and a test
that reached this path fails on it. Rerunning `sminos daemon install` points
the service at the real path, after which this file is dead code; it is
removed once every machine has done so and no image older than the move runs.

It may run under the system's own python3, older than the CLI's own minimum,
before the CLI checks its version: it keeps to Python 3.9.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN = "sminos@doperpowers"


def sibling():
    """The real CLI beside this repository's root, if this copy has one."""
    return os.path.join(HERE, "..", "..", "..", "sminos", "skills", "sminos", "scripts", "sminos.py")


def installed():
    """The installed sminos plugin's CLI: its user (or managed) install record's path."""
    path = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json")
    try:
        with open(path) as f:
            records = ((json.load(f) or {}).get("plugins") or {}).get(PLUGIN) or []
    except (OSError, ValueError, AttributeError):
        return None
    for scope in ("user", "managed"):
        for record in records if isinstance(records, list) else []:
            if isinstance(record, dict) and record.get("scope") == scope and isinstance(record.get("installPath"), str):
                return os.path.join(record["installPath"], "skills", "sminos", "scripts", "sminos.py")
    return None


def main():
    for real in (sibling(), installed()):
        if real is not None and os.path.isfile(real):
            real = os.path.realpath(real)
            sys.stderr.write("sminos: forwarded from the retired path %s; rerun sminos daemon install\n" % os.path.realpath(__file__))
            sys.stderr.flush()
            os.execv(sys.executable, [sys.executable, real] + sys.argv[1:])
    sys.stderr.write("sminos: %s is the CLI's retired path, and the sminos plugin is not beside it or installed "
                     "(%s) — install sminos@doperpowers, then rerun sminos daemon install\n" % (os.path.realpath(__file__), PLUGIN))
    sys.exit(1)


if __name__ == "__main__":
    main()
