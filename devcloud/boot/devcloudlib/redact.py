"""Known values, scrubbed out of everything devcloud persists or forwards: a
command's output before it reaches a log, a service's output before it
reaches the container log, a status detail. File permissions do not stand in
for this — a log never holds a value.

A value is scrubbed in the spellings a command prints by accident — as is,
base64 (padded, unpadded, URL-safe), hex in either case, URL-encoded, and as a
JSON string's body — each replaced by `[secret]`. Values shorter than six
characters are left alone (they would scrub ordinary words), as the guard does."""

import base64
import json
import pathlib
import re
import urllib.parse

from . import envfile

MIN = 6
MARK = b"[secret]"


def spellings(value):
    raw = value.encode() if isinstance(value, str) else value
    out = {raw, base64.b64encode(raw), base64.b64encode(raw).rstrip(b"="), base64.urlsafe_b64encode(raw),
           base64.urlsafe_b64encode(raw).rstrip(b"="), raw.hex().encode(), raw.hex().upper().encode(),
           urllib.parse.quote_from_bytes(raw, safe="").encode()}
    try:
        out.add(json.dumps(raw.decode())[1:-1].encode())
    except UnicodeDecodeError:
        pass
    return {s for s in out if len(s) >= MIN}


class Known:
    def __init__(self, values=()):
        self._values = set()
        self._pattern = None
        self.update(values)

    def add(self, value):
        if not value:
            return
        raw = value.encode() if isinstance(value, str) else bytes(value)
        for form in {raw, raw.rstrip(b"\n"), raw.rstrip(b"\r\n")}:
            if len(form) >= MIN and form not in self._values:
                self._values.add(form)
                self._pattern = None

    def update(self, values):
        for value in values:
            self.add(value)

    def scrub(self, data):
        """`data` (bytes or str, returned in kind) with every known spelling replaced."""
        if not self._values:
            return data
        if self._pattern is None:
            forms = sorted({s for v in self._values for s in spellings(v)}, key=len, reverse=True)
            self._pattern = re.compile(b"|".join(re.escape(f) for f in forms))
        if isinstance(data, str):
            return self._pattern.sub(MARK, data.encode()).decode(errors="replace")
        return self._pattern.sub(MARK, data)


def _read(path):
    try:
        return pathlib.Path(path).read_bytes()
    except OSError:
        return None


def host_values(user, env_path="/etc/devcloud/env"):
    """The secret values already on this host: the store's files (both tiers),
    and each secrets.toml entry's env value and file target (the template's
    value part, or the whole file)."""
    from . import secrets   # here, not at the top: secrets imports proc, which imports this module

    values = set()
    store = user.home / secrets.STORE
    if store.is_dir():
        for path in store.rglob("*"):
            if path.is_file() and not path.is_symlink():
                data = _read(path)
                if data:
                    values.add(data)
    try:
        entries = secrets.parse((user.home / ".claude/devcloud/secrets.toml").read_text())
    except (OSError, ValueError):
        entries = []
    try:
        env = envfile.parse(pathlib.Path(env_path).read_text())
    except (OSError, ValueError):
        env = {}
    for entry in entries:
        if entry.env and env.get(entry.env):
            values.add(env[entry.env].encode())
        if not entry.file:
            continue
        data = _read(user.home / entry.file[2:])
        if not data:
            continue
        if entry.template is None:
            values.add(data)
            continue
        prefix, _, suffix = entry.template.partition("{value}")
        prefix, suffix = prefix.encode(), suffix.replace("{value}", "").encode()
        if data.startswith(prefix) and data.endswith(suffix) and len(data) > len(prefix) + len(suffix):
            values.add(data[len(prefix):len(data) - len(suffix)])
    return {v for v in values if len(v.strip()) >= MIN}


def host_signature(user, env_path="/etc/devcloud/env"):
    """What changes when host_values would: the size and modification time of
    every file it reads. Cheap enough to take before each forwarded output."""
    from . import secrets

    paths = [pathlib.Path(env_path), user.home / ".claude/devcloud/secrets.toml"]
    store = user.home / secrets.STORE
    if store.is_dir():
        paths += sorted(p for p in store.rglob("*") if p.is_file())
    try:
        entries = secrets.parse(paths[1].read_text())
    except (OSError, ValueError):
        entries = []
    paths += [user.home / e.file[2:] for e in entries if e.file]
    signature = []
    for path in paths:
        try:
            st = path.stat()
            signature.append((str(path), st.st_mtime_ns, st.st_size, st.st_ino))
        except OSError:
            signature.append((str(path), None))
    return tuple(signature)
