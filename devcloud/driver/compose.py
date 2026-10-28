"""What `up` composes before it creates anything (§3 steps 3–5): the boot
descriptor (the parent's I5 plus I12), the user-data that stages it, the
labels the create carries (I14), and the recipe hash.

Nothing composed here is secret: the descriptor carries Secret Manager ids,
never values, and a provider keeps user-data readable for the server's life."""

import base64
import decimal
import gzip
import hashlib
import io
import pathlib
import shlex
import tarfile

from devcloudlib import descriptor as host_descriptor
from devcloudlib import envfile, projects as host_projects

from .errors import FAILED, DriverError

# The descriptor is staged here and installed as /etc/devcloud/boot.env only
# after setup.sh (on the slow path) and the seed: setup.sh refuses a machine
# that already holds a descriptor or /var/lib/devcloud (§3 step 4).
STAGE = "/var/lib/devcloud-stage/boot.env"
# Where no seed is delivered (GCE), cloud-init does the first boot itself:
# the recipe it carries on the slow path, and the script that runs it.
RECIPE_STAGE = "/var/lib/devcloud-stage/recipe.tar.gz"
FIRST_BOOT = "/var/lib/devcloud-stage/first-boot.sh"
FIRST_BOOT_LOG = "/var/log/devcloud-first-boot.log"
SRC = "/opt/devcloud-src"
BOOT_ENV = "/etc/devcloud/boot.env"
SETUP_INPUTS = ("DEVCLOUD_USER", "DEVCLOUD_UID", "DEVCLOUD_HOME")
SEED_PATH = "/etc/devcloud/seed/seed.json"
RECIPE_DIRS = ("image", "boot")
# The project whose `devenv up` installs `mawsd`, which provisions the host's endpoint (boot step 13).
MAWS_PROJECT = "maws"


def provisions(profile, projects):
    """Whether a host with `projects` provisions MAWS's endpoint at boot: the
    profile names the v2 code and the projects set up MAWS (by registry name
    or as <owner>/MAWS, any ref). Any other host boots as before."""
    return bool(profile.maws_secret) and any(
        host_projects.devenv_args(entry)[0].lower() == MAWS_PROJECT for entry in projects)


def descriptor(name, profile, projects, expires, creator, spot, seed, adopted=False, *,
               created=None, hourly_price=None, currency=None, creator_project=None):
    """The descriptor's text. `seed` is `file` (the driver delivers the key
    file) or `gce-metadata`; `expires` None means keep (no lease); `adopted`
    marks a machine the driver did not make (§6.5), released at its end."""
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
    if adopted:
        pairs.append(("DEVCLOUD_ADOPTED", "1"))
    if profile.desk_secret:
        pairs.append(("DEVCLOUD_SMINOS_SECRET", profile.desk_secret))
    if provisions(profile, projects):
        pairs += [("DEVCLOUD_MAWS_SECRET", profile.maws_secret),
                  ("DEVCLOUD_MAWS_DELEGATION_ID", profile.delegation_id)]
    for key, value in (("CREATED", created), ("HOURLY_PRICE", hourly_price),
                       ("CURRENCY", currency), ("CREATOR_PROJECT", creator_project)):
        if value is not None:
            rendered = format(decimal.Decimal(str(value)), "f") if key == "HOURLY_PRICE" else str(value)
            pairs.append((f"DEVCLOUD_{key}", rendered))
    text = envfile.format(pairs)
    try:
        host_descriptor.parse(text)
    except host_descriptor.DescriptorError as error:
        raise DriverError(FAILED, f"the descriptor the driver composed does not parse: {error}") from None
    return text


def _file(path, content, append=False, mode="0600"):
    data = content if isinstance(content, bytes) else content.encode()
    entry = (f"  - path: {path}\n    owner: root:root\n    permissions: '{mode}'\n    encoding: b64\n"
             f"    content: {base64.b64encode(data).decode()}\n")
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


def recipe_tar(plugin_dir):
    """The plugin's `image/` and `boot/` as a tar stream, without bytecode."""
    buffer = io.BytesIO()
    root = pathlib.Path(plugin_dir)
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for part in RECIPE_DIRS:
            tar.add(root / part, arcname=f"devcloud/{part}",
                    filter=lambda info: None if "__pycache__" in info.name or info.name.endswith(".pyc") else info)
    return buffer.getvalue()


def recipe_archive(plugin_dir):
    """The recipe gzipped, as GCE's user-data carries it on the slow path."""
    return gzip.compress(recipe_tar(plugin_dir), mtime=0)


def first_boot_script(build, with_recipe):
    """The first boot cloud-init runs where no seed is delivered: on the slow
    path the recipe unpacked and setup.sh run, its exit checked; then the
    staged descriptor ledgered and installed, and the boot started. Its log
    is FIRST_BOOT_LOG."""
    lines = ["#!/bin/bash",
             "# devcloud's first boot where no seed is delivered (the VM driver spec, §3 step 4).",
             "set -uo pipefail",
             f"exec >>{FIRST_BOOT_LOG} 2>&1",
             'echo "first boot $(date -u +%FT%TZ)"']
    if with_recipe:
        missing = [key for key in SETUP_INPUTS if not build.get(key)]
        if missing:
            raise DriverError(FAILED, f"the profile's build.env lacks {missing[0]}, which setup.sh needs")
        inputs = " ".join(f"{key}={shlex.quote(build[key])}" for key in SETUP_INPUTS)
        lines += [f"rm -rf {SRC} && mkdir -p {SRC} && tar -xzf {RECIPE_STAGE} -C {SRC} "
                  "|| { echo 'unpacking the recipe failed'; exit 1; }",
                  f"{inputs} bash {SRC}/devcloud/image/setup.sh >/var/log/devcloud-setup.log 2>&1",
                  "code=$?",
                  'if [ "$code" -ne 0 ]; then echo "setup.sh failed (exit $code): /var/log/devcloud-setup.log"; '
                  "exit 1; fi",
                  f"rm -f {RECIPE_STAGE}"]
    lines += [f"if [ ! -e {BOOT_ENV} ]; then",
              f"  /usr/local/bin/devcloud ledger add {BOOT_ENV} || {{ echo 'devcloud ledger add failed'; exit 1; }}",
              f"  install -m 0600 -o root -g root {STAGE} {BOOT_ENV} || exit 1",
              "fi",
              "systemctl start --no-block devcloud-boot.service",
              'echo "boot started $(date -u +%FT%TZ)"']
    return "\n".join(lines) + "\n"


def boot_user_data(staged_descriptor, keys, recipe, build):
    """cloud-init for a provider with `metadata_seed` (GCE), which does the
    whole first boot (§3 step 4): the keys, the staged descriptor, on the slow
    path the recipe (`recipe`, a gzipped tar; None from an image), and the
    first-boot script, run once by runcmd. Nothing in it is secret."""
    return ("#cloud-config\n"
            "disable_root: false\n"
            "write_files:\n"
            + _file("/root/.ssh/authorized_keys", "".join(key.strip() + "\n" for key in keys), append=True)
            + _file(STAGE, staged_descriptor)
            + (_file(RECIPE_STAGE, recipe) if recipe is not None else "")
            + _file(FIRST_BOOT, first_boot_script(build, recipe is not None), mode="0700")
            + f"runcmd:\n  - [{FIRST_BOOT}]\n")


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
