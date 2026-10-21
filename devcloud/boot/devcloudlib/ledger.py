"""The credential ledger, `/var/lib/devcloud/credentials.ledger` (Design §6.5):
every path where devcloud writes a credential, one absolute path per line,
appended and fsynced before the write. Reconcile never prunes it, so a
target the profile renamed or dropped since it was written is still listed
when the release comes; the release removes every listed path, and the
ledger itself only once every removal has succeeded.

A path in the user's home is removed with the user's own privileges, as it
was written, so a link the user planted there can never steer a root
removal; a link itself is removed, never followed."""

import os
import pathlib
import shutil

PATH = pathlib.Path("/var/lib/devcloud/credentials.ledger")


def entries(path=None):
    try:
        text = pathlib.Path(path or PATH).read_text()
    except FileNotFoundError:
        return []
    return [line for line in text.splitlines() if line.startswith("/")]


def add(target, path=None):
    """Lists `target` (made absolute) before its write; a path already listed
    is not listed again."""
    target = os.path.abspath(str(target))
    if "\n" in target:
        raise ValueError("a ledger path holds no newline")
    if target in entries(path):
        return
    path = pathlib.Path(path or PATH)
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (target + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync_dir(path.parent)


def _sync_dir(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def remove_one(target):
    """Removes `target` whatever it is: a link or a file unlinked, a directory
    removed whole. A target already gone is done."""
    if not os.path.lexists(target):
        return
    if os.path.isdir(target) and not os.path.islink(target):
        shutil.rmtree(target)
    else:
        os.unlink(target)


def remove_all(user, as_user, path=None):
    """Removes every listed path — under the user's home as the user — then
    the ledger, once every removal succeeded. Returns (removed, failures),
    each failure `<path> (<reason>)`; with any failure the ledger stays."""
    removed, failures = [], []
    home = str(user.home).rstrip("/") + "/"
    for target in entries(path):
        try:
            if target.startswith(home):
                as_user(user, lambda target=target: remove_one(target))
            else:
                remove_one(target)
            removed.append(target)
        except Exception as error:  # noqa: BLE001 — every entry is tried; the ledger stays
            failures.append(f"{target} ({type(error).__name__})")
    if not failures:
        pathlib.Path(path or PATH).unlink(missing_ok=True)
    return removed, failures
