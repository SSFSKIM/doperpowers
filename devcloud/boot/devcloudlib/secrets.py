"""The secrets materializer: the profile's `secrets.toml` (Interfaces I3), read
from Secret Manager and written where each entry says.

    [[secret]]
    name = "<Secret Manager secret id>"   # required; latest version is read
    store = "KEY"        # also written as ~/.config/claude-secrets/KEY (I1)
    env = "VAR"          # exported through /etc/devcloud/env
    file = "~/path"      # the value, or the template, written here
    template = "..."     # {value} substituted; without it the file is the value
    mode = "0600"        # default 0600; parent directories created 0700
    optional = true      # absent in Secret Manager -> "missing", boot continues

A payload is written to a store file and to a template-less file byte for
byte. Where it is substituted into a template or exported, its value is the
payload with one trailing newline dropped, the rule the store's readers apply.
Every entry is tried; the step fails after the rest when one required entry
could not be written. Status names secret ids, never a value."""

import dataclasses
import errno
import json
import os
import pathlib
import re
import stat
import tomllib

from . import envfile
from .proc import write_file
from .secretmanager import AccessError

STORE = ".config/claude-secrets"
MANIFEST = pathlib.Path("/var/lib/devcloud/secrets-manifest.json")
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SECRET_ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
_MODE = re.compile(r"0?[0-7]{3}\Z")
_FIELDS = {"name", "store", "env", "file", "template", "mode", "optional"}


class ProfileError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Entry:
    name: str
    store: str | None = None
    env: str | None = None
    file: str | None = None
    template: str | None = None
    mode: int = 0o600
    optional: bool = False


def _string(raw, field, where):
    value = raw.get(field)
    if value is not None and not isinstance(value, str):
        raise ProfileError(f"{where}: {field} must be a string")
    return value


def parse(text):
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ProfileError(f"secrets.toml is not TOML: {error}") from None
    extra = set(data) - {"secret"}
    if extra:
        raise ProfileError(f"secrets.toml: unknown table {', '.join(sorted(extra))}; entries are [[secret]]")
    entries = []
    envs = set()
    for i, raw in enumerate(data.get("secret", []), 1):
        where = f"secrets.toml entry {i}"
        unknown = sorted(set(raw) - _FIELDS)
        if unknown:
            raise ProfileError(f"{where}: unknown field {', '.join(unknown)}")
        name = _string(raw, "name", where)
        if not name or not _SECRET_ID.match(name):
            raise ProfileError(f"{where}: name must be a Secret Manager secret id")
        where = f"secrets.toml entry {name!r}"
        store, env, file, template = (_string(raw, f, where) for f in ("store", "env", "file", "template"))
        if not (store or env or file):
            raise ProfileError(f"{where}: names no target (store, env or file)")
        if store and not _KEY.match(store):
            raise ProfileError(f"{where}: store key must match [A-Za-z_][A-Za-z0-9_]*")
        if env:
            if not envfile.NAME.match(env):
                raise ProfileError(f"{where}: env must be an environment variable name")
            if env in envs:
                raise ProfileError(f"{where}: env {env} is named twice")
            envs.add(env)
        if file:
            if not file.startswith("~/"):
                raise ProfileError(f"{where}: file must start with ~/ (a path in the user's home)")
            _in_home(file, where)
        if template is not None and not file:
            raise ProfileError(f"{where}: a template needs a file")
        mode = raw.get("mode", "0600")
        if not isinstance(mode, str) or not _MODE.match(mode):
            raise ProfileError(f"{where}: mode must be an octal string like \"0600\"")
        optional = raw.get("optional", False)
        if not isinstance(optional, bool):
            raise ProfileError(f"{where}: optional must be true or false")
        entries.append(Entry(name=name, store=store, env=env, file=file, template=template,
                             mode=int(mode, 8), optional=optional))
    return entries


def _in_home(file, where):
    """`file`'s path under the home: refused when it is absolute (`~//etc/x`
    joins to /etc/x), climbs out, or names the home itself. Each path an entry
    writes is listed in the ledger, and the release removes a listed path
    outside the home as root (§6.5)."""
    suffix = pathlib.PurePosixPath(file[2:])
    if suffix.is_absolute() or ".." in suffix.parts or not suffix.parts:
        raise ProfileError(f"{where}: file must name a path inside the home")
    return suffix


@dataclasses.dataclass
class Outcome:
    state: str           # ok | missing | failed
    detail: str
    env: dict            # VAR -> value, for /etc/devcloud/env


def _text(payload):
    text = payload.decode("utf-8")
    return text[:-1] if text.endswith("\n") else text


def _targets(entry, payload):
    """The entry's env value and file bytes, decoded and checked in the
    calling process so a failure is described here, without the value."""
    text = _text(payload) if entry.env or entry.template is not None else None
    if entry.env:
        envfile.format([(entry.env, text)])  # refuses what no env file can hold
    data = None
    if entry.file:
        data = payload if entry.template is None else entry.template.replace("{value}", text).encode()
    return (text if entry.env else None), data


def _identity(st):
    """No values or value hashes: detect replacements and in-place edits."""
    if not stat.S_ISREG(st.st_mode):
        return None
    return [st.st_dev, st.st_ino, st.st_ctime_ns, st.st_mtime_ns,
            st.st_size, st.st_mode, st.st_uid, st.st_gid]


def _file_identity(path):
    try:
        return _identity(path.lstat())
    except FileNotFoundError:
        return None


def _load_owned(home):
    try:
        data = json.loads(MANIFEST.read_text())
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError):
        raise ProfileError("secrets ownership manifest is invalid") from None
    try:
        if data["version"] != 1 or not isinstance(data["home"], str):
            raise ValueError
        files = data["files"]
        if not isinstance(files, dict):
            raise ValueError
        for name, identity in files.items():
            _in_home("~/" + name, "secrets ownership manifest")
            if not isinstance(identity, list) or len(identity) != 8 or any(type(n) is not int for n in identity):
                raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ProfileError("secrets ownership manifest is invalid") from None
    # A different home is not evidence of ownership in this one.
    return files if data["home"] == str(home) else {}


def _save_owned(home, owned):
    write_file(MANIFEST, json.dumps({"version": 1, "home": str(home), "files": owned}) + "\n")


def _remove_owned(home, name, identity):
    """Unlink only the recorded regular file, never through a replaced parent.
    Runs with the same user privileges as materialization, not as root."""
    parts = _in_home("~/" + name, "secrets ownership manifest").parts
    fd = None
    try:
        fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        current = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        if _identity(current) == identity:
            os.unlink(parts[-1], dir_fd=fd)
    except OSError as error:
        if error.errno not in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
            raise
    finally:
        if fd is not None:
            os.close(fd)


def targets(entry, home):
    """The paths an entry writes: its store file and its file, each inside
    `home` (ProfileError otherwise)."""
    home = pathlib.Path(home)
    return (([home / STORE / entry.store] if entry.store else [])
            + ([home / _in_home(entry.file, f"secrets.toml entry {entry.name!r}")] if entry.file else []))


def materialize(entries, fetch, home, as_user=None, before_write=None):
    """Fetches each entry with `fetch(name)` (bytes, or None when absent) and
    writes its targets in `home`, through `as_user(fn)` when given;
    `before_write(path)` is called for each target first, in this process
    (the credential ledger's entry, Design §6.5). A private manifest tracks
    actual writes, allowing removed targets to be pruned without deleting
    user files. Still-declared targets survive transient fetch failures."""
    home = pathlib.Path(home).absolute()
    entries = list(entries)
    run_as = as_user or (lambda fn: fn())
    written, missing, failed = 0, [], []
    env = {}
    owned = _load_owned(home)
    desired = set()
    for entry in entries:
        try:
            desired.update(str(path.relative_to(home)) for path in targets(entry, home))
        except ProfileError:
            pass  # Report this entry's invalid target below, as before.
    for name, identity in list(owned.items()):
        if name in desired:
            continue
        try:
            run_as(lambda: _remove_owned(home, name, identity))
        except Exception as error:  # noqa: BLE001 — retain ownership so cleanup can retry
            failed.append(f"cleanup {name} ({type(error).__name__})")
        else:
            del owned[name]
    _save_owned(home, owned)

    def write_target(path, content, mode):
        (before_write or (lambda path: None))(path)
        before = _file_identity(path)

        def write():
            if path.parent == home / STORE:
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(path.parent, 0o700)
            write_file(path, content, mode=mode)

        run_as(write)
        after = _file_identity(path)
        name = str(path.relative_to(home))
        if after is not None and (after != before or owned.get(name) == after):
            owned[name] = after
        else:
            # write_file leaves identical content alone. Do not claim a user's
            # existing/replaced file merely because it has the desired bytes.
            owned.pop(name, None)
        # Persist each target, including the first half of a failed entry.
        # run_as may fork, so bookkeeping belongs in this parent process.
        _save_owned(home, owned)

    for entry in entries:
        try:
            payload = fetch(entry.name)
        except AccessError as error:
            failed.append(f"{entry.name} ({error})")
            continue
        if payload is None:
            if entry.optional:
                missing.append(entry.name)
            else:
                failed.append(f"{entry.name} (absent from Secret Manager)")
            continue
        try:
            env_value, data = _targets(entry, payload)
            paths = iter(targets(entry, home))  # Validate before ledgering either target.
            if entry.store:
                write_target(next(paths), payload, 0o600)
            if entry.file:
                write_target(next(paths), data, entry.mode)
        except ProfileError as error:
            failed.append(f"{entry.name} ({error})")
            continue
        except UnicodeDecodeError:
            failed.append(f"{entry.name} (not UTF-8 text, which a template or env target needs)")
            continue
        except ValueError:
            failed.append(f"{entry.name} (a value spanning lines cannot be an env target)")
            continue
        except Exception as error:  # noqa: BLE001 — one entry's failure must not stop the rest
            failed.append(f"{entry.name} ({error})")
            continue
        if env_value is not None:
            env[entry.env] = env_value
        written += 1
    parts = [f"{written} written"]
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if failed:
        parts.append("failed: " + ", ".join(failed))
    state = "failed" if failed else "missing" if missing else "ok"
    return Outcome(state=state, detail="; ".join(parts), env=env)
