#!/usr/bin/env python3
"""sminos_hub — this machine's place in its org's hub, as its endpoint gave it.

A machine's enrollment is its endpoint's (`mawsd endpoint enroll|status`).
sminos takes the identity at the endpoint's first welcome over RL10
(sminos_rl10.welcomed writes daemon/identity.json), and that file is the
enrollment from then on: the machine's name, hub and org, and the names it
wrote under before.

- `sminos hub show` prints that identity, read locally. On a machine its
  endpoint never welcomed it says where the enrollment is made, and exits 1.
- `sminos hub enroll`, `check` and `leave` print where the enrollment is
  made now and exit 1. They reach nothing: the words given after them are
  never read or echoed.
- `sminos project init --hub` writes the enrolled hub's org into .smns
  (`add_hub`); a project whose .smns names a hub is never synced through git.

`credential_lock` is held while identity.json is written (sminos_rl10), and
`sessions_under` is the evidence a rename keeps (is_self's `former`).
daemon/hub.json is no enrollment and no credential: its one reader is the
uplink's answer to the endpoint's `legacy-key?` (sminos_uplink.legacy_key_path).
"""

import contextlib
import fcntl
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402

# Where the enrollment is made: what `enroll`, `check` and `leave` say.
ENDPOINTS = "this machine's enrollment is its endpoint's: `mawsd endpoint enroll|status`"
USAGE = "usage: sminos hub show (enroll, check and leave are the endpoint's: mawsd endpoint enroll|status)"


@contextlib.contextmanager
def credential_lock():
    """Held while identity.json is written (sminos_rl10.welcomed): two
    welcomes never interleave their read of the identity and its write."""
    path = daemon.daemon_path("hub.lock")
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def not_welcomed():
    """What a machine its endpoint never welcomed is told: where its
    enrollment is made, and when sminos takes it."""
    return ("%s; sminos takes it at the endpoint's first welcome (sminos daemon status), and until then this "
            "machine is in no hub and writes as %s" % (ENDPOINTS, sminos.host_name()))


def enrolled_hub():
    """This machine's hub, {url, org} (a .smns names only the org): the
    endpoint's identity; exits 1 when the machine has none."""
    ident = rl10.cutover()
    if ident is None:
        sminos.die("this machine is not enrolled at a hub: " + not_welcomed(), 1)
    return {"url": ident["hub"], "org": ident["org"]}


def sessions_under(name):
    """The sessions this installation held under the machine name `name`:
    each with a writer file `<name>.<session>.jsonl` in a project log here,
    and each a seat record whose `host` is `name` holds."""
    held_ = set()
    prefix = name + "."
    for path in glob.glob(os.path.join(glob.escape(sminos.projects_root()), "*", "log", glob.escape(prefix) + "*.jsonl")):
        session = os.path.basename(path)[len(prefix):-len(".jsonl")]
        if sminos.UUID_RE.match(session):
            held_.add(session)
    for s in sminos.seats():
        if s.get("host") == name and s.get("current"):
            held_.add(s["current"])
    return sorted(held_)


def endpoints():
    """`enroll`, `check` and `leave`: exit 1, saying where the enrollment is
    made, with the identity's file on a machine that has one."""
    if not rl10.cut_over():
        sminos.die(not_welcomed(), 1)
    ident = rl10.cutover() or {}
    sminos.die("%s (it cut over to RL10%s; its identity is %s)" % (
        ENDPOINTS, (" on " + ident["cutover"]) if ident.get("cutover") else "", rl10.identity_path()), 1)


def show():
    """The identity the endpoint gave (daemon/identity.json), read locally:
    exit 0 when there is one, 1 when there is none or it cannot be read."""
    if not rl10.cut_over():
        sminos.die(not_welcomed(), 1)
    ident = rl10.cutover()
    if ident is None:
        sminos.die("this machine is cut over to its endpoint, but %s cannot be read: the endpoint's next welcome "
                   "writes it again" % rl10.identity_path(), 1)
    print("machine  %s\nhub      %s (org %s)\nformer   %s\nsince    %s\ncut over %s: RL10 (local-only), the "
          "enrollment is its endpoint's (ref %s); %s holds it, and removing it undoes the cutover" % (
              ident["name"], ident["hub"], ident["org"],
              ", ".join("%s (%d sessions)" % (n, len(s)) for n, s in ident["former"].items()) or "-",
              ident.get("enrolled") or "?", ident.get("cutover") or "?", ident.get("ref") or "?",
              rl10.identity_path()))


def add_hub(path, smns, hub, a):
    """`project init --hub` where .smns exists: the hub field added, every
    other field kept as it is."""
    if a.name or a.remote:
        sminos.die("%s exists: --hub adds the hub to it and changes nothing else — drop --name and --remote" % path)
    if sminos.hub_wellformed(smns[3]) and smns[3]["org"] == hub["org"]:
        print("project %s is already a hub project of org %s" % (smns[1], hub["org"]))
        return
    if smns[3] is not None:
        sminos.die("project %s already names %s: its hub is not changed here" % (
            smns[1], "the hub of org %s" % smns[3]["org"] if sminos.hub_wellformed(smns[3])
            else "a hub that names no org, so it syncs through neither git nor a hub — fix its .smns by hand"), 1)
    # Under the mirror's sync lock: a sync of the project in flight ends
    # first, and every git phase after it reads the hub (ensure_mirrored), so
    # git and the uplink never feed this log at once. The registration both
    # read moves to this checkout under the same hold: a git phase run from
    # another checkout of the project finds the hub there.
    log = os.path.join(sminos.projects_root(), smns[0], "log")
    os.makedirs(log, mode=0o700, exist_ok=True)
    with daemon.sync_op(log):
        with open(path) as f:
            d = json.load(f)
        d["hub"] = {"org": hub["org"]}  # the URL is each machine's enrollment's (sminos.hub_here)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)  # committed: every clone reads it
        os.replace(tmp, path)
        sminos.forget_caches()
        sminos.project_path(sminos.resolve_project(os.path.dirname(path)), "log")
    print("project %s is now a hub project of org %s — commit .smns, so every clone syncs through the hub%s" % (
        smns[1], hub["org"],
        "; its remote %s is no longer synced live (it stays the log's archive)" % smns[2] if smns[2] else ""))


def cmd_hub(words):
    """The `hub` verb. Its words reach no parser that echoes them, and no
    message here names one it did not accept."""
    op = words[0] if words else ""
    if op in ("enroll", "check", "leave"):
        endpoints()
    elif op == "show" and len(words) == 1:
        show()
    else:
        sminos.die(USAGE)
