"""A machine enrolled in its org, as the Python suites make one: cut over as
its endpoint's first welcome leaves it, daemon/identity.json written whole at
mode 0600 (sminos_rl10.welcomed's fields). The shell suites' twin is
rl10-machines.sh's `rl10_cut_over`. A machine's name alone, with no
enrollment, is DAEMON_HOST's; a hub.json enrolls nothing.

    write_identity(sminos_home, name="testhost", former=None, **fields)

`former` is {name: [sessions]}; `fields` override the rest (org, hub, ref,
enrolled, cutover, build). Returns the file's path. The caller forgets its
caches (sminos.forget_caches) when it reads the identity in-process."""

import json
import os

IDENTITY = {"org": "org-1", "hub": "http://127.0.0.1:9", "ref": "machine-ref-1",
            "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"}


def write_identity(sminos_home, name="testhost", former=None, **fields):
    path = os.path.join(sminos_home, "daemon", "identity.json")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({**IDENTITY, "name": name, "former": former or {}, **fields}, f)
    os.replace(tmp, path)
    return path
