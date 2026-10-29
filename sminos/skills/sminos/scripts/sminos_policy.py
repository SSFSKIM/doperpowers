#!/usr/bin/env python3
"""sminos_policy — the machine's policy (DC7 of the desk; DX6's policy, §6).

The daemon is the execution boundary: nothing from outside this machine runs,
and no message written elsewhere is delivered, unless the machine's policy
admits it. The policy is the owner's, kept in `daemon/policy.json` (mode
0600, written whole) and edited through `sminos daemon policy`; it is read at
every use, so an edit holds from the next delivery on, and the uplink
publishes it in DX4's `machine` presence.

    {"read_only": <bool>, "ceiling": <permission mode>}

- `read_only`: when set, nothing that came from outside the machine is
  delivered — an event whose writer is another machine's or the hub's
  (`hub/<member>`) is recorded in the log, settled undelivered, and reported
  `refused-read-only` — while events written on the machine itself deliver
  as before. Every RPC is refused too (sminos_rpc).
- `ceiling`: the loosest permission mode a session spawned from outside may
  run under (sminos_rpc). Absent, it is the mode the user's own settings give
  (`permissions.defaultMode` in ~/.claude/settings.json, read and never
  written; the engine's `default` when they name none).

No file is the default policy: not read-only, the settings' ceiling. A file
that cannot be read as a policy is read as read-only — the owner meant
something, and the boundary fails closed — and said in daemon.log.

On a machine cut over to its endpoint (RL10, sminos_rl10) the endpoint's
policy is the machine's, and the file is its mirror: each `policy` the
endpoint sends is written whole (`take_endpoint`), with the endpoint's last
word kept beside it (`endpoint`). `sminos daemon policy` writes the file as
everywhere, and the uplink, finding it differs from that last word
(`unsent_change`), asks the endpoint (`policy-set`), whose answer writes the
file again. RL10 names the ceiling as O10 does (`wire_policy`): a mode, or
`settings` for the user's settings' defaultMode — a file naming no ceiling.

The known checkouts of a project (where a spawn from outside may run) are
the working directories its sessions joined from on this machine, and the
project's own root.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

POLICY_FILE = "policy.json"
MODES = sminos.PERMISSION_MODES  # least permissive first
FROM_SETTINGS = "settings"
_SAID = {"bad": None}


def policy_path():
    return os.path.join(sminos.root(), "daemon", POLICY_FILE)


def settings_mode():
    """The default mode the user's own settings give (§6): their
    `permissions.defaultMode` as written, else the engine's `default`
    (missing or malformed settings included, as the engine reads them)."""
    try:
        mode = ((sminos.json_at(os.path.join(sminos.home_dir(), ".claude", "settings.json")) or {})
                .get("permissions") or {}).get("defaultMode")
    except (OSError, ValueError, AttributeError):
        mode = None
    return mode if isinstance(mode, str) and mode else "default"


def stored():
    """The policy file as the owner left it: {} when there is none; None when
    it is no policy (unreadable, not JSON, or fields of the wrong kind)."""
    try:
        d = sminos.json_at(policy_path())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("read_only", False), bool) \
            or ("ceiling" in d and d["ceiling"] not in MODES):
        return None
    return d


def load():
    """The policy in force: {"read_only", "ceiling", "ceiling_from"} —
    `ceiling_from` "policy" or "settings". A file that is no policy reads as
    read-only (said once in daemon.log while it stays so)."""
    d = stored()
    if d is None:
        if _SAID["bad"] != policy_path():
            _SAID["bad"] = policy_path()
            sminos.daemon_log("policy: %s is not a policy the daemon can read; the machine is read-only until "
                              "`sminos daemon policy` writes it again" % policy_path())
        return {"read_only": True, "ceiling": settings_mode(), "ceiling_from": FROM_SETTINGS}
    _SAID["bad"] = None
    if "ceiling" in d:
        return {"read_only": d.get("read_only", False), "ceiling": d["ceiling"], "ceiling_from": "policy"}
    return {"read_only": d.get("read_only", False), "ceiling": settings_mode(), "ceiling_from": FROM_SETTINGS}


def machine_policy():
    """The policy as DX4's `machine` presence carries it."""
    p = load()
    return {"read_only": p["read_only"], "ceiling": p["ceiling"]}


def wire_policy():
    """The policy as RL10 says it (O10's): the ceiling a permission mode, or
    `settings` while the file names none — the user's settings' defaultMode,
    which the endpoint reads as `settings` too, so a later change to them
    still holds; DX2's hub takes the mode it resolves to (machine_policy)."""
    p = load()
    return {"read_only": p["read_only"], "ceiling": p["ceiling"] if p["ceiling_from"] == "policy" else FROM_SETTINGS}


def read_only():
    return load()["read_only"]


def outside_origin(e):
    """Whether a log event came from outside this machine: its writer is the
    hub's (`hub/<member>`), `legacy/…`, or another machine's. A writer this
    machine used under a former name, for a session it held then, is its own
    (sminos.is_self)."""
    head, _, _ = str(e.get("writer") or "").rpartition("/")
    return not (head and sminos.is_self(head, sminos.writer_session(e.get("writer") or "")))


def known_checkouts(project, here=None):
    """[{path, branch}]: the project's root while it is still a directory of
    the project (its .smns still names it), and every working directory a
    session of the project joined from on this machine that is still a
    directory of this project — the checkouts a spawn from outside may run
    in (sminos_rpc), as DX4's `machine` presence offers them. None for a
    machine project: a stray's directory resolves to it, and is no checkout.
    `here`: {session: the directory it joined from} of those sessions, as a
    reader that just read the project's view holds it (the uplink's session
    plane); else the view is read. Each directory is looked at once, however
    many sessions joined from it."""
    if sminos.project_kind(project) == "machine":
        return []
    paths = []
    if project.root and os.path.isdir(project.root):
        root = sminos.resolve_project(project.root)
        if root is not None and root.id == project.id:
            paths.append(project.root)
    if here is None:
        here = {}
        for sid, r in sminos.view_of(project, titles=False).info.items():
            j = (r or {}).get("joined") or {}
            machine = str(j.get("machine") or "")
            if not machine or sminos.is_self(machine, sid):
                here[sid] = str(j.get("cwd") or "")
    for cwd in dict.fromkeys(here.values()):
        if not cwd or not os.path.isdir(cwd):
            continue
        p = sminos.resolve_project(cwd)
        if p is not None and p.id == project.id:
            paths.append(cwd)
    return [{"path": p, "branch": git_branch(p)} for p in dict.fromkeys(paths)]


def git_branch(path):
    """The branch checked out at `path`, read from git's HEAD without running
    git; "" when detached or not a checkout."""
    d = os.path.abspath(path)
    while True:
        dot = os.path.join(d, ".git")
        if os.path.exists(dot):
            break
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent
    try:
        # Asked for every member each tick; git writes these files whole, by
        # rename, so a stat tells one unchanged (sminos.file_bytes).
        if os.path.isfile(dot):
            line = sminos.file_bytes(dot).decode().strip()
            dot = os.path.join(d, line[len("gitdir:"):].strip()) if line.startswith("gitdir:") else ""
        head = sminos.file_bytes(os.path.join(dot, "HEAD")).decode().strip()
    except OSError:
        return ""
    return head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else ""


ENDPOINT = "endpoint"   # the policy file's record of the endpoint's last word (RL10)


def endpoint_policy(frame):
    """An endpoint's policy (a `policy` frame, a welcome's), checked:
    {read_only, ceiling}, the ceiling a mode or `settings`; None when it is
    none."""
    if not (isinstance(frame, dict) and isinstance(frame.get("read_only"), bool)
            and frame.get("ceiling") in MODES + (FROM_SETTINGS,)):
        return None
    return {"read_only": frame["read_only"], "ceiling": frame["ceiling"]}


def take_endpoint(p):
    """The endpoint's policy written as the machine's, with its record: a
    ceiling of `settings` is the file naming none."""
    write({"read_only": p["read_only"], **({} if p["ceiling"] == FROM_SETTINGS else {"ceiling": p["ceiling"]}),
           ENDPOINT: dict(p)})


def unsent_change():
    """{field: value} of the policy in force where it differs from the
    endpoint's last word, which the file records: a change made here since;
    {} when there is none, when the endpoint never spoke, or when the file
    is no policy (the endpoint's next word writes it whole)."""
    d = stored()
    heard = endpoint_policy(d.get(ENDPOINT)) if d else None
    if heard is None:
        return {}
    now = wire_policy()
    return {k: now[k] for k in ("read_only", "ceiling") if now[k] != heard[k]}


def write(d):
    path = policy_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    sminos.write_json(path, d)


def describe(p):
    return "read-only: %s\nceiling: %s (%s)" % (
        "yes — nothing written outside this machine is delivered" if p["read_only"] else "no",
        p["ceiling"], "set here" if p["ceiling_from"] == "policy" else "from your settings' defaultMode")


def cmd_policy(a):
    """`sminos daemon policy [--read-only on|off] [--ceiling MODE|settings]`:
    shows the machine's policy, or changes it and shows the result. A change
    nudges the daemon, whose uplink publishes it at once."""
    if a.read_only is None and a.ceiling is None:
        print(describe(load()))
        return
    if a.ceiling is not None and a.ceiling not in MODES + (FROM_SETTINGS,):
        sminos.die("the ceiling is one of %s, or `%s` for your settings' defaultMode" % (
            ", ".join(MODES), FROM_SETTINGS))
    d = stored()
    if d is None:
        d = {"read_only": True}  # a file that was no policy read as read-only: a change keeps that unless it says
    if a.read_only is not None:
        d["read_only"] = a.read_only == "on"
    if a.ceiling == FROM_SETTINGS:
        d.pop("ceiling", None)
    elif a.ceiling is not None:
        d["ceiling"] = a.ceiling
    d.setdefault("read_only", False)
    try:
        write(d)
    except OSError as e:
        sminos.die("the policy could not be written to %s: %s" % (policy_path(), e), 1)
    sminos.nudge_daemon()
    print(describe(load()))
    if sminos.sibling_module("sminos_rl10").cut_over():
        print("This machine's policy is its endpoint's: the daemon's uplink asks the endpoint for this change, and "
              "the policy settles on its answer.")
