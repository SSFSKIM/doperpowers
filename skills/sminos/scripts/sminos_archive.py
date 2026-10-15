#!/usr/bin/env python3
"""sminos_archive — a hub project's log, archived to its git remote (DC4 of
the desk).

A hub project syncs through its hub alone; the `remote` of its .smns keeps
the log's archive. One machine writes it: the one the org's admin designates
for the project (DX7), which the hub tells that machine in `have.archive`, its
answer to every `hello`. The uplink records each answer in the project's
`uplink.json` (`archive`, and `archive_at`, when the hub said it), and says
`hello` again every ARCHIVE_EVERY seconds, so the record is a confirmation at
most one period old. The tick loop, which owns the bounded git phases — git
never runs in the uplink, so a slow push never holds the stream — runs the
archive once for each confirmation naming this machine that no run has used
yet, at most every half period. A machine whose designation moved learns it
at its next confirmation and runs no more; one cut off from the hub receives
none, and runs nothing.

A run works in the clone at `<project home>/archive/`, outside `log/`: it
fetches the remote (bounded, as the mirror's fetches are), starts from
`origin/main` when the remote has one, copies every top-level `*.jsonl` of
`log/` over its namesake whole — never re-sequenced, so the codes and the holes
of spent positions are kept as the log holds them — leaves the files the log
lacks as the remote has them, commits, and pushes. A push the remote rejected
because it moved is retried from a fresh fetch. Nothing is ever read from the
clone into `log/`: git never feeds the live log of a hub project.
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_hublog as hublog  # noqa: E402

# The archive's period; SMINOS_ARCHIVE_EVERY overrides it in seconds, and a
# value of 0 or less turns the archive off on this machine.
ARCHIVE_EVERY = 900
CLONE = "archive"


def archive_every():
    try:
        return float(os.environ.get("SMINOS_ARCHIVE_EVERY") or ARCHIVE_EVERY)
    except ValueError:
        return ARCHIVE_EVERY


def designation(project):
    """(whether the hub's latest answer names this machine the project's
    archive machine, when it answered) as the uplink recorded them."""
    try:
        with open(os.path.join(project.home, hublog.STATE_FILE)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False, 0.0
    if not isinstance(d, dict):
        return False, 0.0
    at = d.get("archive_at")
    return d.get("archive") is True, float(at) if isinstance(at, (int, float)) else 0.0


def due(project, record):
    """Whether this tick runs the archive: a hub project with a remote, the
    archive on here, and a confirmation naming this machine that came after
    the last run began, at least half a period after it."""
    every = archive_every()
    if every <= 0 or not project.remote or not sminos.hub_wellformed(project.hub):
        return False
    designated, at = designation(project)
    last = float((record.get("archive") or {}).get("started") or 0)
    return designated and at > last and time.time() - last >= every / 2


def duty(project, record):
    """The tick's archive duty, its outcome kept in the project's daemon
    record (`record`): (whether a commit was pushed, the error)."""
    if not due(project, record):
        return False, ""
    run_record = record["archive"] = {"started": time.time()}
    try:
        pushed = run(project)
    except daemon.SyncFailed as e:
        run_record["error"] = str(e)
        return False, str(e)
    run_record["pushed"] = pushed
    return bool(pushed), ""


def copy_log(project, clone):
    """Every writer file of log/ over its namesake in the clone, whole: read
    under the file's own lock, so no append is caught half written."""
    log = os.path.join(project.home, "log")
    for path in sorted(glob.glob(os.path.join(glob.escape(log), "*.jsonl"))):
        with sminos.flocked(path + ".lock"):
            with open(path, "rb") as f:
                data = f.read()
        dst = os.path.join(clone, os.path.basename(path))
        try:
            with open(dst, "rb") as f:
                if f.read() == data:
                    continue
        except OSError:
            pass
        with open(dst, "wb") as f:
            f.write(data)


def prepare(project, clone):
    os.makedirs(clone, mode=0o700, exist_ok=True)
    if not os.path.isdir(os.path.join(clone, ".git")):
        daemon.git_ok(clone, "init", "-q", "-b", "main")
    daemon.git_ok(clone, "config", "user.name", "sminos")
    daemon.git_ok(clone, "config", "user.email", "sminos@%s" % sminos.host_name())
    url = daemon.git(clone, "remote", "get-url", "origin")
    if url.returncode != 0:
        daemon.git_ok(clone, "remote", "add", "origin", project.remote)
    elif url.stdout.strip() != project.remote:
        daemon.git_ok(clone, "remote", "set-url", "origin", project.remote)


def push_once(clone):
    return daemon.git(clone, "push", "-q", "origin", "HEAD:main", timeout=daemon.git_timeout())


def run(project):
    """One archive run: the commit pushed, or "" when the remote already held
    the log as it is. SyncFailed when a git step fails or the remote keeps
    moving. One run of a project at a time (`archive.lock`)."""
    clone = os.path.join(project.home, CLONE)
    with sminos.flocked(sminos.project_path(project, "archive.lock")):
        prepare(project, clone)
        daemon.clear_stale_locks(clone)
        for _ in range(daemon.PUSH_RETRIES + 1):
            daemon.fetch(clone)
            if daemon.git(clone, "rev-parse", "--verify", "-q", "origin/main").returncode == 0:
                daemon.git_ok(clone, "reset", "-q", "--hard", "origin/main")
                daemon.git_ok(clone, "clean", "-fdq")
            copy_log(project, clone)
            daemon.git_ok(clone, "add", "-A")
            if daemon.git_ok(clone, "status", "--porcelain").stdout.strip():
                daemon.git_ok(clone, "commit", "-q", "-m", "sminos: %s archives %s" % (sminos.host_name(),
                                                                                       project.name))
            elif not daemon.ahead(clone):
                return ""
            p = push_once(clone)
            if p.returncode == 0:
                return daemon.git_ok(clone, "rev-parse", "HEAD").stdout.strip()
            if not daemon.REJECTED_RE.search((p.stderr or "") + (p.stdout or "")):
                raise daemon.SyncFailed("git push in %s failed: %s" % (clone, daemon.said(p)))
        raise daemon.SyncFailed("git push in %s was rejected %d times: the remote keeps moving"
                                % (clone, daemon.PUSH_RETRIES + 1))
