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
`origin/main` when the remote has one, copies the log's hub-admitted public
projection over the namesakes of its files (copy_log), leaves the files the
log lacks as the remote has them, commits, and pushes. A push the remote
rejected because it moved is retried from a fresh fetch. Nothing is ever read
from the clone into `log/`: git never feeds the live log of a hub project.

The admitted public projection (P5 O18 D6): the archive's remote is the
project's, readable by the whole org, so it holds only what the hub admitted
to every reader. No audience stream (`<writer>~<digest>`) ever enters it.
A plain writer of another machine is copied as imported — whole, never
re-sequenced, so the codes and the holes of spent positions are kept as the
log holds them. This machine's own (under its name or a former one,
`HubLog.is_own`) is copied up to the hub's vector in the `have` that
confirmed the run (`archive_have` in uplink.json, saved with `archive_at`;
a former name's entry as the last `have` under that name saved it, and none
copied without one: sminos_hublog's on_have), never `sent` or `taken`: on RL10 `taken` moves once the endpoint's socket
takes a frame, before the hub admitted or refused anything in it. Each
position that `have` lists withheld, each this machine recorded refused
`audience` or voided (sminos_hublog's `dead` and `voided`), is written as
its tombstone, `{writer, seq, withheld: true}`, whatever the local file
holds there: a refusal lost to a dropped connection is still honoured, and
a refused body never reaches the archive once a void fills its position.
Below a `conflict` kept (uplink-taken.json), the hub holds another event, so
nothing from there on is copied. Past that frontier (frozen for a former
name, lowered by a conflict) the archive's file keeps what it already holds,
up to the last position this machine wrote or the hub's vector: the run
replaces only the prefix it confirms, so the archive never loses a position
another archiver or an earlier run gave it. A run with no usable `archive_have` fails.
"""

import glob
import json
import os
import re
import shutil
import stat
import sys
import tempfile
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
    if every <= 0 or not project.remote or not sminos.hub_synced(project.hub):
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


def held_as_file(dst):
    """The bytes of a regular file at dst, never read through a symlink; None
    for anything else there, or nothing."""
    try:
        if not stat.S_ISREG(os.lstat(dst).st_mode):
            return None
        fd = os.open(dst, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        return f.read()


STREAM_FILE = re.compile(r"~[0-9a-f]{16}\.jsonl$")


def admitted(project):
    """What the run copies this machine's own writers by: (the hub's
    admitted vector {writer: seq}, {writer: [(from, to)]} of the positions
    written as tombstones, {writer: seq} below which nothing is copied for a
    conflict). daemon.SyncFailed when the last `have` confirmed nothing
    usable (none saved yet, or one sminos_hublog.admitted_have refused)."""
    hl = hublog.HubLog(project, {"key": None, "machine": sminos.host_name()}, coded=False)
    d = hl.state()
    ah = d.get("archive_have")
    if not (isinstance(ah, dict) and isinstance(ah.get("have"), dict) and isinstance(ah.get("withheld"), dict)):
        raise daemon.SyncFailed("the archive of %s waits for a have from the hub that confirms what it admitted%s"
                                % (project.name, ": %s" % d["archive_have_error"] if d.get("archive_have_error") else ""))
    have = {w: s for w, s in ah["have"].items() if type(s) is int}
    marked = {}
    for w, raw in ah["withheld"].items():
        try:
            marked[w] = hublog.runs_of(raw)
        except ValueError as e:
            raise daemon.SyncFailed("the archive of %s: its saved withheld list of %s is unreadable (%s)"
                                    % (project.name, w, e))
    for source in (hl.dead(), hl.voided()):
        for w, held in source.items():
            seqs = held["at"] if isinstance(held, dict) else held
            marked.setdefault(w, []).extend((s, s) for s in seqs)
    return have, marked, hl.conflicts(), hl.is_own


def archived_seq(line, writer):
    """The position a line of the archive's file holds for `writer` — an
    event's or a tombstone's —, or None."""
    try:
        e = json.loads(line.decode("utf-8", "replace"))
    except ValueError:
        return None
    if isinstance(e, dict) and e.get("writer") == writer and type(e.get("seq")) is int and e["seq"] > 0:
        return e["seq"]
    return None


def admitted_bytes(data, writer, top, marked, archived=None, head=0):
    """An own writer file's admitted projection: its lines up to `top`, each
    position in `marked` (runs) its tombstone instead, whatever the file holds
    there (nothing included), in seq order; a line no event parses from is
    no admitted position, and is left out. Past `top`, `archived` — the bytes
    the archive already holds for the writer — keeps each position it holds
    up to the last this machine wrote or `head`, the hub's vector for it
    (a tombstone for one in `marked`): a frontier frozen or lowered below
    what the archive holds says nothing of those positions, so the archive
    never loses one, and nothing local past `top` is ever copied. Up to
    `top` the projection replaces what the archive holds, and a line past
    both bounds, beyond anything this machine or the hub held of the
    writer, is no position of it (the remote edited), and is left out."""
    lines, last = {}, 0
    for line in data.split(b"\n"):
        e = sminos.parse_event(line.decode("utf-8", "replace")) if line.strip() else None
        if e is not None:
            last = max(last, e["seq"])
        if e is None or e["seq"] > top or hublog.in_runs(e["seq"], marked):
            continue
        lines.setdefault(e["seq"], []).append(line)
    for a, b in marked:
        for seq in range(a, min(b, top) + 1):
            lines[seq] = [json.dumps(hublog.tombstone(writer, seq), ensure_ascii=False).encode("utf-8")]
    kept = {}
    for line in (archived or b"").split(b"\n"):
        seq = archived_seq(line, writer) if line.strip() else None
        if seq is not None and top < seq <= max(last, head):
            kept.setdefault(seq, []).append(line)
    for seq in kept:
        lines[seq] = ([json.dumps(hublog.tombstone(writer, seq), ensure_ascii=False).encode("utf-8")]
                      if hublog.in_runs(seq, marked) else kept[seq])
    return b"".join(line + b"\n" for seq in sorted(lines) for line in lines[seq])


def copy_log(project, clone):
    """The log's admitted public projection (the module's) over the
    namesakes of its files at the clone's top — each file read under its own
    lock, so no append is caught half written — and the names copied. Each
    is written as a regular file by rename inside the clone: whatever the
    remote put at that name (a symlink, which the reset checked out as one, a
    directory) is replaced, never written through, so nothing the remote
    holds can steer a write out of the clone."""
    log = os.path.join(project.home, "log")
    have, marked, conflicts, own = admitted(project)
    names = []
    for path in sorted(glob.glob(os.path.join(glob.escape(log), "*.jsonl"))):
        name = os.path.basename(path)
        if STREAM_FILE.search(name):
            continue
        with sminos.flocked(path + ".lock"):
            with open(path, "rb") as f:
                data = f.read()
        writer = next((e["writer"] for e in map(sminos.parse_event, data.decode("utf-8", "replace").split("\n"))
                       if e is not None), None)
        if writer is None or sminos.is_stream(writer):
            continue
        dst = os.path.join(clone, name)
        if own(writer):
            top = have.get(writer, 0)
            if writer in conflicts:
                top = min(top, conflicts[writer] - 1)
            if top <= 0:
                continue
            # Over the file the remote holds (none through a symlink): what it holds past this run's frontier of
            # this machine's or the hub's positions is kept.
            data = admitted_bytes(data, writer, top, sorted(marked.get(writer, [])), held_as_file(dst),
                                  have.get(writer, 0))
        names.append(name)
        if held_as_file(dst) == data:
            continue
        if os.path.isdir(dst) and not os.path.islink(dst):
            shutil.rmtree(dst)
        fd, tmp = tempfile.mkstemp(dir=clone, prefix=".sminos-archive-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, dst)  # a rename replaces a symlink itself, never its target
        finally:
            if os.path.lexists(tmp):
                os.unlink(tmp)
    return names


# The writer files are archived byte for byte, whatever the remote's
# .gitattributes say: no eol conversion, no ident, no filter, no encoding.
# $GIT_DIR/info/attributes outranks every .gitattributes in the tree.
ATTRIBUTES = "*.jsonl -text -ident -filter -diff -merge -working-tree-encoding\n"


def prepare(project, clone):
    os.makedirs(clone, mode=0o700, exist_ok=True)
    if not os.path.isdir(os.path.join(clone, ".git")):
        daemon.git_ok(clone, "init", "-q", "-b", "main")
    daemon.git_ok(clone, "config", "user.name", "sminos")
    daemon.git_ok(clone, "config", "user.email", "sminos@%s" % sminos.host_name())
    daemon.git_ok(clone, "config", "core.autocrlf", "false")
    info = os.path.join(clone, ".git", "info")
    os.makedirs(info, exist_ok=True)
    with open(os.path.join(info, "attributes"), "w") as f:
        f.write(ATTRIBUTES)
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
            names = copy_log(project, clone)
            if names:
                # Named, and forced past the remote's ignore rules: a writer
                # file is archived whatever .gitignore says; nothing else the
                # remote holds is touched.
                daemon.git_ok(clone, "add", "-f", "--", *names)
            if daemon.git(clone, "diff", "--cached", "--quiet").returncode != 0:
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
