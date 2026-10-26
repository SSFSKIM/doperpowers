#!/usr/bin/env python3
"""sminos_media — a desk upload's files on this machine (the desk control
surface's MW5: image and PDF intake).

The `media` RPC's bytes are written where a Read of them asks nothing: under
the session's live working directory, at
`<cwd>/.claude/desk-uploads/<session>/<nonce>.<n>.<ext>` (§10, §11). Every
component below the resolved working directory is opened relative to the one
before it and never through a link, so a link planted at `.claude`,
`desk-uploads`, the session's directory or a file's own name refuses the
upload rather than redirect the write; each file is created exclusively,
mode 0600, its extension the one its bytes' signature names (the native
Read picks image or PDF handling by it; the name the person gave is for
display only). Saving is idempotent: a file already there with the same
bytes is taken as saved, so a daemon restart may save one upload again.

Each root a session's uploads went to is recorded at
`daemon/uploads/<session>.json` before anything is written under it, and the
daemon sweeps those roots, again without following a link, once the session
runs nowhere here and has been quiet as long as its bridge's kept file must
be (sminos_daemon.sweep_uploads). The repository's `info/exclude` gets one
line, so an upload never shows in `git status`.
"""

import base64
import binascii
import errno
import json
import os
import re
import stat
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

# DX6 `media`: each type with its stored extension and its bytes' signature.
TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
ATTACHMENTS_MAX = 4
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
UPLOADS = (".claude", "desk-uploads")   # under the working directory; the session's directory below them
EXCLUDE_LINE = "**/.claude/desk-uploads/"   # unanchored: a session in a subdirectory of the checkout matches too
GIT_TIMEOUT = 10
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_records = threading.Lock()


class Unsafe(Exception):
    """A component of the upload's path that is a link, not a directory, or a
    file there already holding other bytes: nothing is written through it."""


def type_of(data):
    """The media type the bytes' signature names, or None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def decoded(text):
    """The bytes of standard base64 text, strictly (no other character, padded
    as encoded), or None."""
    if not isinstance(text, str) or not text:
        return None
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    return data if data and base64.b64encode(data).decode("ascii") == text else None


def why_not(attachments):
    """Why DX6 `media`'s attachments are not its shape, or None: 1-4 of them,
    each a name, one of the five types, and base64 bytes whose signature is
    that type."""
    if not (isinstance(attachments, list) and 1 <= len(attachments) <= ATTACHMENTS_MAX):
        return "attachments is a list of 1-%d files" % ATTACHMENTS_MAX
    for i, a in enumerate(attachments):
        if not isinstance(a, dict):
            return "attachment %d is {name, mediaType, data}" % i
        if not (isinstance(a.get("name"), str) and NAME_RE.fullmatch(a["name"])):
            return "attachment %d's name is [A-Za-z0-9][A-Za-z0-9._-]{0,127}" % i
        if a.get("mediaType") not in TYPES:
            return "attachment %d's mediaType is one of %s" % (i, ", ".join(TYPES))
        data = decoded(a.get("data"))
        if data is None:
            return "attachment %d's data is base64 bytes" % i
        if type_of(data) != a["mediaType"]:
            return "attachment %d's bytes are not %s" % (i, a["mediaType"])
    return None


def file_name(nonce, n, media_type):
    return "%s.%d.%s" % (nonce, n, TYPES[media_type])


def root_of(base, session):
    return os.path.join(base, *UPLOADS, session)


def _open_dir(fd, name, create):
    """The directory `name` under `fd`, opened without following a link;
    created 0700 when missing and `create`. Unsafe when it is a link or not a
    directory."""
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=fd)
        except FileExistsError:
            pass
    try:
        return os.open(name, DIR_FLAGS, dir_fd=fd)
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            raise Unsafe("%s is a link or not a directory: nothing is written through it" % name) from e
        raise


def _walk(base, session, create):
    """The upload root's fd, every component below `base` walked by _open_dir."""
    fd = os.open(base, DIR_FLAGS)
    try:
        for name in (*UPLOADS, session):
            nxt = _open_dir(fd, name, create)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write(fd, name, data):
    """`data` at `name` under `fd`, created exclusively, mode 0600; a file
    already there with the same bytes is taken as saved. Unsafe otherwise."""
    try:
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    except FileExistsError:
        try:
            held = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except OSError as e:
            if e.errno == errno.ELOOP:
                raise Unsafe("%s is a link: nothing is written through it" % name) from e
            raise
        with os.fdopen(held, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode) or f.read() != data:
                raise Unsafe("%s is already there, holding other bytes" % name)
        return
    with os.fdopen(out, "wb") as f:
        f.write(data)


def save(base, session, nonce, attachments):
    """An upload's attachments (DX6's, already checked by why_not) written
    under `base`, the session's resolved working directory: (root, the files'
    names in order). Its root is recorded first, so the sweep finds what a
    crash leaves. Raises Unsafe, or OSError."""
    root = root_of(base, session)
    record(session, root)
    fd = _walk(base, session, True)
    try:
        names = []
        for n, a in enumerate(attachments):
            name = file_name(nonce, n, a["mediaType"])
            _write(fd, name, decoded(a["data"]))
            names.append(name)
        return root, names
    finally:
        os.close(fd)


def remove(root, names=None):
    """The files `names` (every file, when None) under an upload root
    removed, walked as they were written, never through a link; the root
    itself too when that empties it. What cannot be reached safely is left."""
    up, session = os.path.split(root)
    base = os.path.dirname(os.path.dirname(up))
    try:
        fd = _walk(base, session, False)
    except (Unsafe, OSError):
        return
    try:
        for name in os.listdir(fd) if names is None else names:
            try:
                if not stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                    os.unlink(name, dir_fd=fd)
            except OSError:
                pass
        left = os.listdir(fd)
    finally:
        os.close(fd)
    if not left:
        try:
            ufd = os.open(up, DIR_FLAGS)
        except OSError:
            return
        try:
            os.rmdir(session, dir_fd=ufd)
        except OSError:
            pass
        finally:
            os.close(ufd)


def exclude(base):
    """The upload directories excluded from the repository `base` is in
    (its common `info/exclude`, which every worktree of it reads): True once
    the line is there, False when `base` is in no repository."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    r = subprocess.run(["git", "-C", base, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True, timeout=GIT_TIMEOUT, env=env)
    common = r.stdout.strip()
    if r.returncode != 0 or not os.path.isabs(common):
        return False
    path = os.path.join(common, "info", "exclude")
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    if EXCLUDE_LINE in text.splitlines():
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(("" if not text or text.endswith("\n") else "\n") + EXCLUDE_LINE + "\n")
    return True


# ------------------------------------------------------------- the records


def records_dir():
    return os.path.join(sminos.root(), "daemon", "uploads")


def record_path(session):
    return os.path.join(records_dir(), session + ".json")


def roots(session):
    """The upload roots recorded for a session."""
    try:
        with open(record_path(session)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    return [r for r in d if isinstance(r, str) and os.path.isabs(r)] if isinstance(d, list) else []


def record(session, root):
    """`root` kept among the session's upload roots. Raises OSError."""
    with _records:
        held = roots(session)
        if root in held:
            return
        os.makedirs(records_dir(), mode=0o700, exist_ok=True)
        sminos.write_json(record_path(session), held + [root])


def recorded():
    """The sessions with upload roots recorded."""
    try:
        names = os.listdir(records_dir())
    except OSError:
        return []
    return [s for s, ext in map(os.path.splitext, names) if ext == ".json" and sminos.UUID_RE.fullmatch(s)]


def sweep(session):
    """Every upload root of the session removed, then its record."""
    with _records:
        for root in roots(session):
            remove(root)
        try:
            os.unlink(record_path(session))
        except OSError:
            pass
