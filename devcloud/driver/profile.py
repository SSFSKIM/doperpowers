"""The person's driver profile (I10): `driver.toml` beside `build.env` in the
profile's `devcloud/` directory. Every key is checked here, unknown ones
refused, so a typo fails the command naming the key rather than surfacing as
a default much later."""

import dataclasses
import pathlib
import re
import tomllib

from devcloudlib import envfile

from .errors import USAGE, DriverError

SHIPPED = ("hetzner", "gce")
_ACCOUNT = re.compile(r"[a-z0-9][a-z0-9-]{0,39}\Z")
_PROVIDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SECRET_ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
_VAR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DURATION = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?\Z")


def duration(text):
    """Seconds in `35m`, `12h`, `3d`, `1h30m`; ValueError otherwise."""
    m = _DURATION.match(text or "")
    if not text or not m or not any(m.groups()):
        raise ValueError(f"{text!r} is not a duration like 35m, 12h or 3d")
    days, hours, minutes, seconds = (int(g or 0) for g in m.groups())
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError(f"{text!r} is not a positive duration")
    return total


def format_duration(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    out = (f"{hours}h" if hours else "") + (f"{minutes}m" if minutes else "") + (f"{secs}s" if secs else "")
    return out or "0s"


@dataclasses.dataclass(frozen=True)
class Caps:
    unconfirmed: int = 3
    lease_default: int | None = None   # seconds of a VM's lease without --ttl; None: kept
    vcpu_max: int = 8
    max_disk_gb: int = 200


@dataclasses.dataclass(frozen=True)
class Host:
    sm_project: str
    config_repo: str
    config_branch: str
    config_token_secret: str
    tailscale_secret: str


@dataclasses.dataclass(frozen=True)
class Account:
    name: str
    provider: str
    location: str
    type: str
    env: dict
    vars: dict
    registered: str | None

    @property
    def shipped(self):
        return self.provider in SHIPPED


@dataclasses.dataclass(frozen=True)
class Profile:
    dir: pathlib.Path
    caps: Caps
    default_account: str
    host: Host
    desk_secret: str | None
    accounts: dict
    build: dict

    def account(self, name):
        if name not in self.accounts:
            known = ", ".join(sorted(self.accounts))
            raise DriverError(USAGE, f"the profile has no account {name!r} (it has {known})")
        return self.accounts[name]

    @property
    def toml(self):
        return self.dir / "driver.toml"


def _bad(message):
    return DriverError(USAGE, f"driver.toml: {message}")


def _only(table, allowed, where):
    if not isinstance(table, dict):
        raise _bad(f"{where} is not a table")
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise _bad(f"unknown key {', '.join(unknown)} in {where}")


def _string(table, key, where, pattern=None, required=True):
    value = table.get(key)
    if value is None:
        if required:
            raise _bad(f"{where} lacks {key}")
        return None
    if not isinstance(value, str) or not value or (pattern and not pattern.match(value)):
        raise _bad(f"{where}.{key} is not valid")
    return value


# Keys whose meaning changed when VMs became kept by default (spec Decision Log, 2026-10-27): refused
# by name rather than read, so a profile does not go on looking set.
_REPLACED = {"throwaway": "renamed unconfirmed, which counts kept VMs as well as leased ones",
             "lease_max": "leases have no lifetime cap any more; remove it"}


def _caps(table):
    replaced = sorted(set(table) & set(_REPLACED)) if isinstance(table, dict) else []
    if replaced:
        raise _bad("; ".join(f"[caps].{key} is gone: {_REPLACED[key]}" for key in replaced))
    _only(table, ("unconfirmed", "lease_default", "vcpu_max", "max_disk_gb"), "[caps]")
    values = {}
    for key in ("unconfirmed", "vcpu_max", "max_disk_gb"):
        if key in table:
            if not isinstance(table[key], int) or isinstance(table[key], bool) or table[key] < 0:
                raise _bad(f"[caps].{key} is not a whole number")
            values[key] = table[key]
    if "lease_default" in table and table["lease_default"] != "keep":
        try:
            values["lease_default"] = duration(table["lease_default"]) if isinstance(table["lease_default"], str) \
                else duration("")
        except ValueError:
            raise _bad("[caps].lease_default is not keep or a duration like 12h") from None
    return Caps(**values)


def _host(table):
    keys = ("sm_project", "config_repo", "config_branch", "config_token_secret", "tailscale_secret")
    _only(table, keys, "[host]")
    repo = _string(table, "config_repo", "[host]")
    if not repo.startswith("https://"):
        raise _bad("[host].config_repo must be an https clone URL")
    return Host(sm_project=_string(table, "sm_project", "[host]"), config_repo=repo,
                config_branch=_string(table, "config_branch", "[host]", required=False) or "main",
                config_token_secret=_string(table, "config_token_secret", "[host]", _SECRET_ID),
                tailscale_secret=_string(table, "tailscale_secret", "[host]", _SECRET_ID))


def _mapping(table, key, where, value_pattern=None):
    value = table.get(key, {})
    if not isinstance(value, dict):
        raise _bad(f"{where}.{key} is not a table")
    for name, item in value.items():
        if not _VAR.match(name) or not isinstance(item, str) or (value_pattern and not value_pattern.match(item)):
            raise _bad(f"{where}.{key}.{name} is not valid")
    return dict(value)


def _account(table, index):
    where = f"[[account]] #{index + 1}"
    _only(table, ("name", "provider", "location", "type", "env", "vars", "registered"), where)
    name = _string(table, "name", where, _ACCOUNT)
    where = f"account {name}"
    return Account(name=name, provider=_string(table, "provider", where, _PROVIDER),
                   location=_string(table, "location", where), type=_string(table, "type", where),
                   env=_mapping(table, "env", where, _SECRET_ID), vars=_mapping(table, "vars", where),
                   registered=_string(table, "registered", where, _SHA, required=False))


def load(directory):
    directory = pathlib.Path(directory)
    path = directory / "driver.toml"
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        raise DriverError(USAGE, f"no driver.toml in the profile ({directory})") from None
    except tomllib.TOMLDecodeError as error:
        raise _bad(f"does not parse ({error})") from None
    _only(data, ("caps", "defaults", "host", "desk", "account"), "the top level")
    caps = _caps(data.get("caps", {}))
    defaults = data.get("defaults", {})
    _only(defaults, ("account",), "[defaults]")
    host = _host(data.get("host", {}))
    desk = data.get("desk", {})
    _only(desk, ("provisioning_secret",), "[desk]")
    accounts = {}
    raw = data.get("account", [])
    if not isinstance(raw, list) or not raw:
        raise _bad("no [[account]]")
    for index, table in enumerate(raw):
        account = _account(table, index)
        if account.name in accounts:
            raise _bad(f"account {account.name} twice")
        accounts[account.name] = account
    default = _string(defaults, "account", "[defaults]")
    if default not in accounts:
        raise _bad(f"[defaults].account names {default!r}, which no [[account]] is")
    return Profile(dir=directory, caps=caps, default_account=default, host=host,
                   desk_secret=_string(desk, "provisioning_secret", "[desk]", _SECRET_ID, required=False),
                   accounts=accounts, build=_build(directory))


def _build(directory):
    try:
        text = (directory / "build.env").read_text()
    except FileNotFoundError:
        return {}
    try:
        return envfile.parse(text)
    except ValueError as error:
        raise DriverError(USAGE, f"build.env: {error}") from None
