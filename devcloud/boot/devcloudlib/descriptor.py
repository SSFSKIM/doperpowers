"""The boot descriptor, `/etc/devcloud/boot.env` (Interfaces I5, with the
driver's additions I12): the only per-host input a driver supplies. Every key
is checked here, so a typo fails the boot at its first step rather than
surfacing as a default much later.

`DEVCLOUD_EXPIRES`, the lease, is the one key the host rewrites itself
(`devcloud lease set`, `set_expires`); a lease end in the past is accepted, so
a host rebooted after its lease still boots, and then departs."""

import dataclasses
import math
import re

from . import envfile

PATH = "/etc/devcloud/boot.env"

REQUIRED = ("DEVCLOUD_NAME", "DEVCLOUD_KIND", "DEVCLOUD_ROLE", "DEVCLOUD_TAILSCALE", "DEVCLOUD_SEED",
            "DEVCLOUD_SM_PROJECT", "DEVCLOUD_CONFIG_REPO", "DEVCLOUD_CONFIG_TOKEN_SECRET")
OPTIONAL = ("DEVCLOUD_TS_SECRET", "DEVCLOUD_TS_AUTHKEY_FILE", "DEVCLOUD_CONFIG_BRANCH", "DEVCLOUD_PROJECTS", "DEVCLOUD_MIRROR_DIR",
            # I12, the driver's: the lease and who hears of its end, the inbound policy, adoption,
            # the desk's provisioning key, a spot VM; MAWS's provisioning code and its delegation (P5 O14).
            "DEVCLOUD_EXPIRES", "DEVCLOUD_CREATOR", "DEVCLOUD_INBOUND", "DEVCLOUD_ADOPTED", "DEVCLOUD_SMINOS_SECRET",
            "DEVCLOUD_SPOT", "DEVCLOUD_MAWS_SECRET", "DEVCLOUD_MAWS_DELEGATION_ID",
            "DEVCLOUD_CREATED", "DEVCLOUD_HOURLY_PRICE", "DEVCLOUD_CURRENCY", "DEVCLOUD_CREATOR_PROJECT")

_HOSTNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_PROJECT = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?(?:@\S+)?\Z")
_SECRET_ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
# A sminos tag a lease warning can reach: @alias, @alias#short, @short, @project/alias.
_CREATOR = re.compile(r"@[A-Za-z0-9][A-Za-z0-9._/-]*(?:#[0-9a-f]+)?\Z")
_UNIX = re.compile(r"[0-9]{1,12}\Z")
# A delegation's id in the org state (RL5): public, so the descriptor carries the value.
_DELEGATION_ID = re.compile(r"[0-9a-f]{32}\Z")


class DescriptorError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Descriptor:
    name: str
    kind: str          # vm | microvm | container
    role: str          # persistent | sandbox
    tailscale: str     # join | host | none
    ts_secret: str | None        # join: the Secret Manager id of the Tailscale OAuth client
    ts_authkey_file: str | None  # join, the fallback: a one-time auth key's file
    seed_kind: str     # file | gce-metadata
    seed_path: str | None
    sm_project: str
    config_repo: str
    config_branch: str
    config_token_secret: str
    projects: tuple
    mirror_dir: str | None
    expires: int | None = None       # the lease end, Unix seconds; None: no lease (keep)
    creator: str | None = None       # the sminos tag the lease warning goes to
    inbound: str = "open"            # tailnet: the public port closes once the tailnet is up
    adopted: bool = False            # the lease end, and down, run release
    sminos_secret: str | None = None  # the desk provisioning key's Secret Manager id
    spot: bool = False               # a spot VM: the reclaim unit is enabled
    maws_secret: str | None = None   # the MAWS provisioning code's Secret Manager id (boot step 13)
    maws_delegation_id: str | None = None  # its delegation's id, the prefix of the machine's ref

    created: int | None = None
    hourly_price: float | None = None
    currency: str | None = None
    creator_project: str | None = None

    @property
    def leased(self):
        return self.expires is not None


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
    ts_secret = values.get("DEVCLOUD_TS_SECRET") or None
    authkey = values.get("DEVCLOUD_TS_AUTHKEY_FILE") or None
    if tailscale == "join":
        if role == "sandbox":
            raise DescriptorError("a sandbox never joins the tailnet as its own node: "
                                  "DEVCLOUD_TAILSCALE=join needs DEVCLOUD_ROLE=persistent")
        if not (ts_secret or authkey):
            raise DescriptorError("DEVCLOUD_TAILSCALE=join needs DEVCLOUD_TS_SECRET or DEVCLOUD_TS_AUTHKEY_FILE")
        if ts_secret and authkey:
            raise DescriptorError("name one of DEVCLOUD_TS_SECRET (the OAuth client) and "
                                  "DEVCLOUD_TS_AUTHKEY_FILE (the fallback), not both")
        if ts_secret and not _SECRET_ID.match(ts_secret):
            raise DescriptorError("DEVCLOUD_TS_SECRET is not a Secret Manager secret id")
    elif ts_secret or authkey:
        # A host that does not join never fetches or holds the tailnet's credential.
        raise DescriptorError(f"{'DEVCLOUD_TS_SECRET' if ts_secret else 'DEVCLOUD_TS_AUTHKEY_FILE'} "
                              "is for DEVCLOUD_TAILSCALE=join only")

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

    mirror_dir = values.get("DEVCLOUD_MIRROR_DIR") or None
    if mirror_dir and not mirror_dir.startswith("/"):
        raise DescriptorError("DEVCLOUD_MIRROR_DIR must be an absolute path")

    lifecycle = _lifecycle(values, role, tailscale)
    return Descriptor(
        name=name, kind=kind, role=role, tailscale=tailscale, ts_secret=ts_secret, ts_authkey_file=authkey,
        seed_kind=seed_kind, seed_path=seed_path, sm_project=values["DEVCLOUD_SM_PROJECT"],
        config_repo=repo, config_branch=values.get("DEVCLOUD_CONFIG_BRANCH") or "main",
        config_token_secret=token_secret, projects=projects,
        mirror_dir=mirror_dir, **lifecycle, **_notice(values),
    )


def _flag(values, key):
    value = values.get(key)
    if value is None or value == "":
        return False
    if value != "1":
        raise DescriptorError(f"{key} is {value!r}; it is 1 or absent")
    return True


def _lifecycle(values, role, tailscale):
    """I12's keys: the ones a sandbox never carries (a lease, adoption, an
    enrollment) refused on one, so a typo in the role cannot make a sandbox
    depart or enroll."""
    expires = values.get("DEVCLOUD_EXPIRES") or None
    if expires is not None:
        if not _UNIX.match(expires):
            raise DescriptorError(f"DEVCLOUD_EXPIRES is {expires!r}; expected Unix seconds")
        expires = int(expires)
    creator = values.get("DEVCLOUD_CREATOR") or None
    if creator is not None and not _CREATOR.match(creator):
        raise DescriptorError(f"DEVCLOUD_CREATOR {creator!r} is not a sminos tag (@alias, @alias#short)")
    inbound = values.get("DEVCLOUD_INBOUND") or "open"
    if inbound not in ("tailnet", "open"):
        raise DescriptorError(f"DEVCLOUD_INBOUND is {inbound!r}; expected one of tailnet, open")
    if inbound == "tailnet" and tailscale != "join":
        raise DescriptorError("DEVCLOUD_INBOUND=tailnet closes every door but the tailnet's: it needs "
                              "DEVCLOUD_TAILSCALE=join")
    adopted = _flag(values, "DEVCLOUD_ADOPTED")
    spot = _flag(values, "DEVCLOUD_SPOT")
    sminos_secret = values.get("DEVCLOUD_SMINOS_SECRET") or None
    if sminos_secret is not None and not _SECRET_ID.match(sminos_secret):
        raise DescriptorError("DEVCLOUD_SMINOS_SECRET is not a Secret Manager secret id")
    maws_secret, delegation = _maws(values, sminos_secret)
    if role == "sandbox":
        for key, present in (("DEVCLOUD_EXPIRES", expires is not None), ("DEVCLOUD_ADOPTED", adopted),
                             ("DEVCLOUD_SMINOS_SECRET", sminos_secret), ("DEVCLOUD_SPOT", spot),
                             ("DEVCLOUD_MAWS_SECRET", maws_secret)):
            if present:
                raise DescriptorError(f"{key} is for a persistent host: a sandbox never carries a lease, "
                                      "is never adopted, a spot VM or enrolled")
    return dict(expires=expires, creator=creator, inbound=inbound, adopted=adopted,
                sminos_secret=sminos_secret, spot=spot, maws_secret=maws_secret, maws_delegation_id=delegation)


def _maws(values, sminos_secret):
    """MAWS's provisioning code and its delegation's id, both or neither: the
    code is redeemed only under a ref the id prefixes. A host that enrolls
    sminos on DX2 holds a phase-1 row under its name, which refuses the
    certificate (409 name-taken), so it never names the code as well."""
    secret = values.get("DEVCLOUD_MAWS_SECRET") or None
    delegation = values.get("DEVCLOUD_MAWS_DELEGATION_ID") or None
    if (secret is None) != (delegation is None):
        raise DescriptorError("DEVCLOUD_MAWS_SECRET and DEVCLOUD_MAWS_DELEGATION_ID go together")
    if secret is not None and not _SECRET_ID.match(secret):
        raise DescriptorError("DEVCLOUD_MAWS_SECRET is not a Secret Manager secret id")
    if delegation is not None and not _DELEGATION_ID.match(delegation):
        raise DescriptorError("DEVCLOUD_MAWS_DELEGATION_ID is not a delegation id (32 lower-case hex digits)")
    if secret is not None and sminos_secret is not None:
        raise DescriptorError("DEVCLOUD_SMINOS_SECRET enrolls sminos on DX2, whose row under the name refuses the "
                              "certificate DEVCLOUD_MAWS_SECRET provisions: name one of them")
    return secret, delegation


def _notice(values):
    created = values.get("DEVCLOUD_CREATED") or None
    if created is not None:
        if not _UNIX.fullmatch(created):
            raise DescriptorError("DEVCLOUD_CREATED must be Unix seconds")
        created = int(created)
    price = values.get("DEVCLOUD_HOURLY_PRICE") or None
    if price is not None:
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", price) or not math.isfinite(float(price)):
            raise DescriptorError("DEVCLOUD_HOURLY_PRICE must be a nonnegative finite decimal")
        price = float(price)
    currency = values.get("DEVCLOUD_CURRENCY") or None
    if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
        raise DescriptorError("DEVCLOUD_CURRENCY must be a three-letter ISO currency code")
    project = values.get("DEVCLOUD_CREATOR_PROJECT") or None
    if project is not None and (not re.fullmatch(r"[^\s(),]+", project) or project.startswith("-")):
        raise DescriptorError("DEVCLOUD_CREATOR_PROJECT must name one sminos project")
    return dict(created=created, hourly_price=price, currency=currency, creator_project=project)


def set_expires(text, expires):
    """The descriptor's text with DEVCLOUD_EXPIRES set to `expires`, every
    other line as it was; the line is added when the descriptor had none.
    `expires` None removes the lease (the host is kept)."""
    lines = text.splitlines(keepends=True)
    line = f"DEVCLOUD_EXPIRES={int(expires)}\n" if expires is not None else ""
    out, done = [], False
    for each in lines:
        if re.match(r"\s*(?:export\s+)?DEVCLOUD_EXPIRES=", each):
            if not done:
                out.append(line)
                done = True
            continue
        out.append(each)
    if not done and line:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(line)
    return "".join(out)


def load(path=PATH, allow_http=False):
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        raise DescriptorError(f"no boot descriptor at {path}") from None
    return parse(text, allow_http=allow_http)
