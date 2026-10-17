"""The boot descriptor, `/etc/devcloud/boot.env` (Interfaces I5): the only
per-host input a driver supplies. Every key is checked here, so a typo fails
the boot at its first step rather than surfacing as a default much later."""

import dataclasses
import re

from . import envfile

PATH = "/etc/devcloud/boot.env"

REQUIRED = ("DEVCLOUD_NAME", "DEVCLOUD_KIND", "DEVCLOUD_ROLE", "DEVCLOUD_TAILSCALE", "DEVCLOUD_SEED",
            "DEVCLOUD_SM_PROJECT", "DEVCLOUD_CONFIG_REPO", "DEVCLOUD_CONFIG_TOKEN_SECRET")
OPTIONAL = ("DEVCLOUD_TS_AUTHKEY_FILE", "DEVCLOUD_CONFIG_BRANCH", "DEVCLOUD_PROJECTS", "DEVCLOUD_MIRROR_DIR")

_HOSTNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_PROJECT = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?(?:@\S+)?\Z")
_SECRET_ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")


class DescriptorError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Descriptor:
    name: str
    kind: str          # vm | microvm | container
    role: str          # persistent | sandbox
    tailscale: str     # join | host | none
    ts_authkey_file: str | None
    seed_kind: str     # file | gce-metadata
    seed_path: str | None
    sm_project: str
    config_repo: str
    config_branch: str
    config_token_secret: str
    projects: tuple
    mirror_dir: str | None


def _one_of(values, key, allowed):
    value = values[key]
    if value not in allowed:
        raise DescriptorError(f"{key} is {value!r}; expected one of {', '.join(allowed)}")
    return value


def parse(text, allow_http=False):
    try:
        values = envfile.parse(text)
    except ValueError as error:
        raise DescriptorError(f"boot descriptor: {error}") from None
    unknown = sorted(set(values) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise DescriptorError(f"unknown key {', '.join(unknown)} in the boot descriptor")
    missing = [key for key in REQUIRED if not values.get(key)]
    if missing:
        raise DescriptorError(f"the boot descriptor lacks {', '.join(missing)}")

    name = values["DEVCLOUD_NAME"]
    if not _HOSTNAME.match(name):
        raise DescriptorError(f"DEVCLOUD_NAME {name!r} is not a host name (letters, digits, inner hyphens)")
    kind = _one_of(values, "DEVCLOUD_KIND", ("vm", "microvm", "container"))
    role = _one_of(values, "DEVCLOUD_ROLE", ("persistent", "sandbox"))
    tailscale = _one_of(values, "DEVCLOUD_TAILSCALE", ("join", "host", "none"))
    authkey = values.get("DEVCLOUD_TS_AUTHKEY_FILE") or None
    if tailscale == "join":
        if role == "sandbox":
            raise DescriptorError("a sandbox never joins the tailnet as its own node: "
                                  "DEVCLOUD_TAILSCALE=join needs DEVCLOUD_ROLE=persistent")
        if not authkey:
            raise DescriptorError("DEVCLOUD_TAILSCALE=join needs DEVCLOUD_TS_AUTHKEY_FILE")

    seed = values["DEVCLOUD_SEED"]
    if seed == "gce-metadata":
        seed_kind, seed_path = "gce-metadata", None
    elif seed.startswith("file:/"):
        seed_kind, seed_path = "file", seed[len("file:"):]
    else:
        raise DescriptorError("DEVCLOUD_SEED is neither file:<absolute path> nor gce-metadata")

    repo = values["DEVCLOUD_CONFIG_REPO"]
    if not (repo.startswith("https://") or (allow_http and repo.startswith("http://"))):
        raise DescriptorError("DEVCLOUD_CONFIG_REPO must be an https clone URL")
    token_secret = values["DEVCLOUD_CONFIG_TOKEN_SECRET"]
    if not _SECRET_ID.match(token_secret):
        raise DescriptorError("DEVCLOUD_CONFIG_TOKEN_SECRET is not a Secret Manager secret id")

    projects = tuple(values.get("DEVCLOUD_PROJECTS", "").split())
    for entry in projects:
        if not _PROJECT.match(entry):
            raise DescriptorError(f"DEVCLOUD_PROJECTS entry {entry!r} is not <name>[@ref] or <owner>/<repo>[@ref]")

    return Descriptor(
        name=name, kind=kind, role=role, tailscale=tailscale, ts_authkey_file=authkey,
        seed_kind=seed_kind, seed_path=seed_path, sm_project=values["DEVCLOUD_SM_PROJECT"],
        config_repo=repo, config_branch=values.get("DEVCLOUD_CONFIG_BRANCH") or "main",
        config_token_secret=token_secret, projects=projects,
        mirror_dir=values.get("DEVCLOUD_MIRROR_DIR") or None,
    )


def load(path=PATH, allow_http=False):
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        raise DescriptorError(f"no boot descriptor at {path}") from None
    return parse(text, allow_http=allow_http)
