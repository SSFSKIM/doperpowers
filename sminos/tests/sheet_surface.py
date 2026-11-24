#!/usr/bin/env python3
"""The stand-in surface: a question sheet's surface registration, written and heartbeated, so a session offers the
sheet where no page runs yet (plan docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, "Words"; the
registration is composite §7's, sminos/types/sheet/schema/surface.schema.json). It answers nothing: questions are
answered with `sminos sheet answer` or `put`.

    sheet_surface.py [--name standin] [--url http://sheet.localhost:47590] [--reach local|remote] [--every 10]

writes $SMINOS_HOME/sheet/surfaces/<name>.json with its own pid, rewrites it every `--every` seconds (by atomic
replace), and removes it on SIGTERM or SIGINT. `--once` writes it and exits, leaving a registration whose pid is gone
(not alive).
"""

import argparse
import datetime
import json
import os
import signal
import sys
import time


def path(name):
    home = os.environ.get("SMINOS_HOME") or os.path.join(os.path.expanduser("~"), ".claude", "sminos")
    return os.path.join(home, "sheet", "surfaces", name + ".json")


def write(p, reg):
    os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
    t = datetime.datetime.now(datetime.timezone.utc)
    reg = dict(reg, heartbeatAt=t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000))
    tmp = p + ".tmp-%d" % os.getpid()          # its name does not end in .json, so no reader takes it
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(json.dumps(reg) + "\n")
    os.replace(tmp, p)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="standin")
    ap.add_argument("--url", default="http://sheet.localhost:47590")
    ap.add_argument("--reach", choices=("local", "remote"), default="local")
    ap.add_argument("--every", type=float, default=10.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    p = path(a.name)
    reg = {"v": 1, "name": a.name, "pid": os.getpid(), "url": a.url, "reach": a.reach}
    write(p, reg)
    if a.once:
        return 0

    def stop(*_):
        try:
            os.unlink(p)
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        time.sleep(a.every)
        write(p, reg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
