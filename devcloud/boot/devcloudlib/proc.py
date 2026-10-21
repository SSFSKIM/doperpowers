"""Running things as root or as the host's user, and writing files safely.

Commands' output goes to a root-only log under /var/log/devcloud, never to the
status file, and only after every known value is scrubbed out of it (a tool
may print what it was given; a log never holds a value).
Work in the user's home runs with the user's own privileges (`as_user`), so a
path planted in the home can never steer a root write."""

import dataclasses
import os
import pathlib
import pwd
import subprocess

from . import envfile, redact

IMAGE_ENV = "/etc/devcloud/image.env"
LOG_DIR = pathlib.Path("/var/log/devcloud")
SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# The values this process knows; steps add the bootstrap token, access tokens
# and every payload as they read them, and the host's own on loading.
KNOWN = redact.Known()


class StepError(Exception):
    """A step's failure; the message is its status detail, so it names no value."""


@dataclasses.dataclass(frozen=True)
class User:
    name: str
    uid: int
    gid: int
    home: pathlib.Path

    @classmethod
    def from_image(cls, path=IMAGE_ENV):
        """The user the image was built for (Design §2's build inputs)."""
        try:
            with open(path) as f:
                name = envfile.parse(f.read())["DEVCLOUD_USER"]
        except (OSError, KeyError, ValueError) as error:
            raise StepError(f"{path} does not name the image's user ({type(error).__name__})") from None
        entry = pwd.getpwnam(name)
        return cls(name=name, uid=entry.pw_uid, gid=entry.pw_gid, home=pathlib.Path(entry.pw_dir))

    def env(self, extra=None):
        """A clean login-like environment for the user, as systemd's User= gives."""
        env = {
            "HOME": str(self.home), "USER": self.name, "LOGNAME": self.name, "SHELL": "/usr/bin/zsh",
            "PATH": f"{self.home}/.local/bin:{SYSTEM_PATH}", "LANG": "C.UTF-8",
        }
        env.update(extra or {})
        return env


def _drops(user):
    return user is not None and os.geteuid() == 0 and user.uid != 0


def as_user(user, fn):
    """Runs `fn()` with the user's uid and gid in a forked child (directly when
    there is nothing to drop). An exception in the child becomes a StepError
    carrying its type and message, which callers keep free of values."""
    if not _drops(user):
        fn()
        return
    read, write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read)
        code = 0
        try:
            os.setgroups([])
            os.setgid(user.gid)
            os.setuid(user.uid)
            os.umask(0o022)
            fn()
        except BaseException as error:  # noqa: BLE001 — reported to the parent, then exit
            os.write(write, f"{type(error).__name__}: {error}"[:500].encode())
            code = 1
        finally:
            os._exit(code)
    os.close(write)
    with os.fdopen(read, "rb") as f:
        message = f.read().decode(errors="replace")
    _, wait_status = os.waitpid(pid, 0)
    if os.waitstatus_to_exitcode(wait_status) != 0:
        raise StepError(message or "the child exited without a message")


def log_path(name):
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return LOG_DIR / f"{name}.log"


LOG_LINES = 200


def _write_log(log, argv, output):
    """Appends a command's header and its last LOG_LINES lines of output to
    its log, every known value scrubbed first."""
    lines = output.splitlines(keepends=True)
    head = f"--- {' '.join(pathlib.Path(a).name if i == 0 else a for i, a in enumerate(argv))}\n".encode()
    if len(lines) > LOG_LINES:
        head += f"[{len(lines) - LOG_LINES} earlier lines dropped]\n".encode()
    body = b"".join(lines[-LOG_LINES:])
    if body and not body.endswith(b"\n"):
        body += b"\n"
    fd = os.open(log_path(log), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as f:
        f.write(KNOWN.scrub(head + body))


def run(argv, *, user=None, env=None, log=None, input=None, capture=False, timeout=600, cwd=None):
    """Runs `argv` (as `user` when given). Its output (stderr only, when
    `capture` returns stdout) goes to the log `log` names, scrubbed of every
    known value and cut to its last lines; without a log it is dropped.
    Raises StepError naming the command and the log on a nonzero exit."""
    label = " ".join(pathlib.Path(argv[0]).name if i == 0 else a for i, a in enumerate(argv[:2]))
    kwargs = {}
    if _drops(user):
        kwargs.update(user=user.uid, group=user.gid, extra_groups=[])
    where = f" (log {log_path(log)})" if log else ""
    try:
        result = subprocess.run(
            argv, env=env, cwd=cwd, timeout=timeout,
            input=input.encode() if isinstance(input, str) else input,
            stdin=None if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE if capture else subprocess.STDOUT, **kwargs,
        )
    except FileNotFoundError:
        raise StepError(f"{label}: command not found") from None
    except subprocess.TimeoutExpired as expired:
        if log:
            partial = (expired.stderr if capture else expired.stdout) or b""
            _write_log(log, argv, partial)
        raise StepError(f"{label} timed out after {timeout}s{where}") from None
    if log:
        _write_log(log, argv, (result.stderr if capture else result.stdout) or b"")
    if result.returncode != 0:
        raise StepError(f"{label} exited {result.returncode}{where}")
    return result.stdout.decode() if capture else None


def call(argv, *, user=None, env=None, log=None, input=None, timeout=600, cwd=None):
    """Runs `argv` as `run` does, but returns its exit status rather than
    raising on one: (exit, stdout, stderr's last line), both scrubbed. A
    timeout is exit 124, a missing command 127."""
    kwargs = {}
    if _drops(user):
        kwargs.update(user=user.uid, group=user.gid, extra_groups=[])
    try:
        result = subprocess.run(
            argv, env=env, cwd=cwd, timeout=timeout,
            input=input.encode() if isinstance(input, str) else input,
            stdin=None if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs,
        )
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired as expired:
        if log:
            _write_log(log, argv, (expired.stdout or b"") + (expired.stderr or b""))
        return 124, "", f"timed out after {timeout}s"
    if log:
        _write_log(log, argv, (result.stdout or b"") + (result.stderr or b""))
    err = [line for line in KNOWN.scrub(result.stderr or b"").decode(errors="replace").splitlines() if line.strip()]
    return result.returncode, KNOWN.scrub(result.stdout or b"").decode(errors="replace"), err[-1] if err else ""


def write_file(path, data, mode=0o600, dir_mode=0o700):
    """Writes `data` to `path` through a new file renamed over it: the target
    is replaced, never written through (a symlink there is replaced, not
    followed), and the file has `mode` before it holds a byte. Missing parent
    directories are made with `dir_mode`. Unchanged content is left alone."""
    path = pathlib.Path(path)
    for parent in reversed(path.parents):
        if not parent.exists():
            parent.mkdir(mode=dir_mode)
            os.chmod(parent, dir_mode)
    if isinstance(data, str):
        data = data.encode()
    try:
        st = os.lstat(path)
        if (not os.path.islink(path) and (st.st_mode & 0o7777) == mode
                and st.st_size == len(data) and path.read_bytes() == data):
            return False
    except FileNotFoundError:
        pass
    tmp = path.with_name(f".{path.name}.devcloud-{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return True
