"""What `up` composes before it creates anything (§3 steps 3–5): the boot
descriptor (the parent's I5 plus I12), the user-data that stages it, the
labels the create carries (I14), and the recipe hash.

Nothing composed here is secret: the descriptor carries Secret Manager ids,
never values, and a provider keeps user-data readable for the server's life."""

import base64
import hashlib
import pathlib

from devcloudlib import descriptor as host_descriptor
from devcloudlib import envfile

from .errors import FAILED, DriverError

# The descriptor is staged here and installed as /etc/devcloud/boot.env only
# after setup.sh (on the slow path) and the seed: setup.sh refuses a machine
# that already holds a descriptor or /var/lib/devcloud (§3 step 4).
STAGE = "/var/lib/devcloud-stage/boot.env"
SEED_PATH = "/etc/devcloud/seed/seed.json"
RECIPE_DIRS = ("image", "boot")


def descriptor(name, profile, projects, expires, creator, spot, seed):
    """The descriptor's text. `seed` is `file` (the driver delivers the key
    file) or `gce-metadata`; `expires` None means keep (no lease)."""
    host = profile.host
    pairs = [
        ("DEVCLOUD_NAME", name), ("DEVCLOUD_KIND", "vm"), ("DEVCLOUD_ROLE", "persistent"),
        ("DEVCLOUD_TAILSCALE", "join"), ("DEVCLOUD_TS_SECRET", host.tailscale_secret),
        ("DEVCLOUD_SEED", f"file:{SEED_PATH}" if seed == "file" else "gce-metadata"),
        ("DEVCLOUD_SM_PROJECT", host.sm_project), ("DEVCLOUD_CONFIG_REPO", host.config_repo),
        ("DEVCLOUD_CONFIG_BRANCH", host.config_branch), ("DEVCLOUD_CONFIG_TOKEN_SECRET", host.config_token_secret),
        ("DEVCLOUD_INBOUND", "tailnet"),
    ]
    if projects:
        pairs.append(("DEVCLOUD_PROJECTS", " ".join(projects)))
    if expires is not None:
        pairs.append(("DEVCLOUD_EXPIRES", str(int(expires))))
    if creator:
        pairs.append(("DEVCLOUD_CREATOR", creator))
    if spot:
        pairs.append(("DEVCLOUD_SPOT", "1"))
    if profile.desk_secret:
        pairs.append(("DEVCLOUD_SMINOS_SECRET", profile.desk_secret))
    text = envfile.format(pairs)
    try:
        host_descriptor.parse(text)
    except host_descriptor.DescriptorError as error:
        raise DriverError(FAILED, f"the descriptor the driver composed does not parse: {error}") from None
    return text


def _file(path, content, append=False):
    entry = (f"  - path: {path}\n    owner: root:root\n    permissions: '0600'\n    encoding: b64\n"
             f"    content: {base64.b64encode(content.encode()).decode()}\n")
    return entry + ("    append: true\n" if append else "")


def user_data(staged_descriptor, keys):
    """cloud-init that authorizes the driver keys for root and stages the
    descriptor (§3 step 4); with no descriptor (an image's builder, §7) only
    the keys. Each file's content is base64, so no value needs YAML quoting.
    The rest — setup.sh, the seed, boot.env, the boot's start — is the
    driver's over SSH where a seed is delivered."""
    authorized = "".join(key.strip() + "\n" for key in keys)
    return ("#cloud-config\n"
            "disable_root: false\n"
            "write_files:\n"
            + _file("/root/.ssh/authorized_keys", authorized, append=True)
            + (_file(STAGE, staged_descriptor) if staged_descriptor is not None else ""))


def labels(kind, lifetime, expires, by, creator, recipe, confirmed, enroll, test_run):
    out = {"devcloud": kind, "devcloud-lifetime": lifetime}
    if expires is not None:
        out["devcloud-expires"] = str(int(expires))
    out["devcloud-by"] = by
    if creator:
        out["devcloud-creator"] = creator
    out["devcloud-recipe"] = recipe
    if confirmed:
        out["devcloud-confirmed"] = "1"
    if enroll:
        out["devcloud-enroll"] = enroll
    if test_run:
        out["devcloud-test"] = test_run
    return out


def recipe_hash(plugin_dir):
    """SHA-256 over the sorted relative paths and bytes of the plugin's
    `image/` and `boot/` (the recipe a host is built from), 12 hex; bytecode
    caches left out, since they differ by machine."""
    root = pathlib.Path(plugin_dir)
    digest = hashlib.sha256()
    files = sorted(p for d in RECIPE_DIRS for p in (root / d).rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    for path in files:
        rel = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(4, "big") + rel + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()[:12]
